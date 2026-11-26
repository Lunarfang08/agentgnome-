from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from agentgenome.db import Approval, Database, Genome, Run, SimOrder, ToolAction, uid
from agentgenome.genome import Manifest
from agentgenome.providers import FixtureProvider
from agentgenome.service import TERMINAL, digest, emit, expired, finish, scoped


async def advance(
    database: Database, run_id: str, tenant: str, *, fault_after_commit: bool = False
) -> str:
    """Execute one fixture step. All committed effects and checkpoint writes are idempotent."""
    async with database.session(tenant) as session:
        run = await scoped(session, Run, run_id, tenant, lock=True)
        if run.state in TERMINAL:
            return run.state
        genome = await scoped(session, Genome, run.genome_id, tenant)
        manifest = Manifest.model_validate(genome.manifest)
        limits = manifest.spec.limits
        cp = dict(run.checkpoint)
        if expired(run, limits.maxWallSeconds):
            await finish(session, run, "TIMED_OUT", {"code": "deadline"})
            return run.state
        if (
            cp["step"] >= manifest.spec.harness.maxIterations
            or cp["tokens"] + 48 > limits.maxTotalTokens
        ):
            await finish(session, run, "BUDGET_EXHAUSTED", {"code": "iteration_or_token_limit"})
            return run.state
        # Test fixture has a fixed 48-token ceiling; live provider metering is not yet admitted.
        response = await FixtureProvider().generate(run.task, cp["observations"])
        if response.kind == "final":
            await emit(session, run, "run.verifying", {})
            order = await session.scalar(
                select(SimOrder).where(SimOrder.run_id == run.id, SimOrder.tenant_id == tenant)
            )
            if order is None:
                await finish(session, run, "FAILED", {"code": "missing_order"})
            else:
                await finish(
                    session,
                    run,
                    "SUCCEEDED",
                    {"output": response.output, "order_id": order.id, "simulated": True},
                )
            return run.state
        tool = response.tool
        if tool not in manifest.spec.tools.allowed:
            await emit(session, run, "tool.denied", {"tool": tool})
            await finish(session, run, "FAILED", {"code": "tool_denied"})
            return run.state
        if cp["tool_calls"] >= manifest.spec.tools.maxCalls:
            await finish(session, run, "BUDGET_EXHAUSTED", {"code": "tool_limit"})
            return run.state
        arguments_hash = digest(response.arguments)
        action = await session.scalar(
            select(ToolAction).where(
                ToolAction.run_id == run.id,
                ToolAction.tenant_id == tenant,
                ToolAction.step == cp["step"],
            )
        )
        if action is None:
            action = ToolAction(
                id=uid(),
                tenant_id=tenant,
                run_id=run.id,
                step=cp["step"],
                tool=tool,
                arguments_hash=arguments_hash,
                state="PREPARED",
            )
            session.add(action)
            await session.flush()
            await emit(session, run, "tool.prepared", {"action_id": action.id, "tool": tool})
        if action.arguments_hash != arguments_hash or action.tool != tool:
            await finish(session, run, "FAILED", {"code": "action_mismatch"})
            return run.state
        if tool == "orders.submit":
            approval = await session.scalar(
                select(Approval)
                .where(Approval.action_id == action.id, Approval.tenant_id == tenant)
                .with_for_update()
            )
            if approval is None:
                approval = Approval(
                    tenant_id=tenant,
                    run_id=run.id,
                    action_id=action.id,
                    arguments_hash=arguments_hash,
                    status="PENDING",
                    expires_at=datetime.now(UTC) + timedelta(minutes=15),
                )
                session.add(approval)
                run.state = "WAITING_APPROVAL"
                await emit(
                    session,
                    run,
                    "approval.required",
                    {"action_id": action.id, "arguments": response.arguments},
                )
                return run.state
            if approval.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
                await finish(session, run, "FAILED", {"code": "approval_expired"})
                return run.state
            if approval.status == "REJECTED":
                await finish(session, run, "FAILED", {"code": "approval_rejected"})
                return run.state
            if approval.status not in {"APPROVED", "CONSUMED"}:
                return "WAITING_APPROVAL"
            if approval.arguments_hash != action.arguments_hash:
                await finish(session, run, "FAILED", {"code": "approval_mismatch"})
                return run.state
            run.state = "RUNNING"
            if action.state == "UNKNOWN":
                order = await session.scalar(
                    select(SimOrder).where(
                        SimOrder.action_id == action.id, SimOrder.tenant_id == tenant
                    )
                )
                if order is None:
                    await finish(session, run, "FAILED", {"code": "reconciliation_required"})
                    return run.state
                action.state, action.receipt = "RECONCILED", {"order_id": order.id}
                await emit(session, run, "tool.reconciled", {"action_id": action.id})
            elif action.state == "PREPARED":
                if approval.status != "APPROVED":
                    await finish(session, run, "FAILED", {"code": "approval_replayed"})
                    return run.state
                approval.status = "CONSUMED"
                order = SimOrder(
                    id=uid(),
                    tenant_id=tenant,
                    run_id=run.id,
                    action_id=action.id,
                    item=response.arguments["item"],
                    quantity=response.arguments["quantity"],
                )
                session.add(order)
                action.receipt = {"order_id": order.id}
                action.state = "UNKNOWN" if fault_after_commit else "CONFIRMED"
                if fault_after_commit:
                    await emit(session, run, "tool.unknown", {"action_id": action.id})
                    return "RUNNING"
        else:
            action.state = "CONFIRMED"
            action.receipt = (
                {"items": [{"item": "paper", "stock": 10}]}
                if tool == "inventory.read"
                else {"prepared": True, **response.arguments}
            )
        cp["step"] += 1
        cp["tokens"] += response.input_tokens + response.output_tokens
        cp["tool_calls"] += 1
        cp["observations"] = [*cp["observations"], {"tool": tool, "result": action.receipt}]
        run.checkpoint, run.state = cp, "RUNNING"
        await emit(
            session,
            run,
            "tool.completed",
            {"action_id": action.id, "tool": tool, "result": action.receipt},
        )
        await emit(session, run, "run.checkpointed", {"step": cp["step"], "tokens": cp["tokens"]})
        return run.state
