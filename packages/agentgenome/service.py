import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentgenome.auth import Identity
from agentgenome.db import Audit, Base, Genome, Outbox, Run, RunEvent, Tenant
from agentgenome.genome import Manifest

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "BUDGET_EXHAUSTED"}
T = TypeVar("T", bound=Base)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def scoped(
    session: AsyncSession, model: type[T], object_id: str, tenant: str, *, lock: bool = False
) -> T:
    query = select(model).where(model.id == object_id, model.tenant_id == tenant)  # type: ignore[attr-defined]
    if lock:
        query = query.with_for_update()
    obj = await session.scalar(query)
    if obj is None:
        raise HTTPException(404, "resource not found")
    return obj


def audit(session: AsyncSession, identity: Identity, operation: str, resource: str) -> None:
    session.add(
        Audit(
            tenant_id=identity.tenant_id,
            actor=identity.subject,
            operation=operation,
            resource_id=resource,
        )
    )


async def emit(session: AsyncSession, run: Run, kind: str, payload: dict[str, Any]) -> None:
    run.sequence += 1
    session.add(
        RunEvent(
            tenant_id=run.tenant_id,
            run_id=run.id,
            sequence=run.sequence,
            kind=kind,
            payload=payload,
        )
    )


async def finish(session: AsyncSession, run: Run, state: str, result: dict[str, Any]) -> None:
    if run.state in TERMINAL:
        return
    run.state, run.result = state, result
    await emit(session, run, "run." + state.lower(), result)
    await session.execute(
        update(Tenant)
        .where(Tenant.id == run.tenant_id)
        .values(reserved=Tenant.reserved - run.reserved_cost, spent=Tenant.spent + run.actual_cost)
    )


async def admit(
    session: AsyncSession, identity: Identity, genome: Genome, task: str, key: str
) -> Run:
    identity.require("run")
    request_hash = digest({"genome_id": genome.id, "task": task})
    # Tenant lock serializes admission and duplicate-key checks across API replicas.
    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == identity.tenant_id).with_for_update()
    )
    if tenant is None:
        raise HTTPException(404, "tenant not found")
    existing = await session.scalar(
        select(Run).where(Run.tenant_id == identity.tenant_id, Run.idempotency_key == key)
    )
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, "idempotency key already used for another request")
        return existing
    if not genome.published or not genome.digest:
        raise HTTPException(409, "publish genome before admission")
    manifest = Manifest.model_validate(genome.manifest)
    if manifest.spec.model.route != "deterministic-procurement":
        raise HTTPException(
            422, "only the explicitly enabled deterministic route is executable in this increment"
        )
    if manifest.spec.harness.strategy != "plan-execute-verify":
        raise HTTPException(422, "harness strategy not implemented")
    if manifest.spec.skills or manifest.spec.memory.namespaces or manifest.spec.evolution.enabled:
        raise HTTPException(422, "skills, memory and evolution execution are not implemented")
    if manifest.spec.tools.programmaticCalling:
        raise HTTPException(422, "programmatic calling is not implemented")
    if manifest.spec.sandbox.profile != "trusted-fixture":
        raise HTTPException(422, "hardened sandbox profile is not available")
    if not set(manifest.spec.tools.allowed) <= {
        "inventory.read",
        "orders.prepare",
        "orders.submit",
    }:
        raise HTTPException(422, "unregistered tool")
    amount = manifest.spec.limits.maxCostUsd
    updated = await session.execute(
        update(Tenant)
        .where(
            Tenant.id == identity.tenant_id,
            Tenant.budget - Tenant.spent - Tenant.reserved >= amount,
        )
        .values(reserved=Tenant.reserved + amount)
    )
    if updated.rowcount != 1:  # type: ignore[attr-defined]
        raise HTTPException(429, "tenant budget exhausted")
    run = Run(
        tenant_id=identity.tenant_id,
        genome_id=genome.id,
        genome_hash=genome.digest,
        task=task,
        request_hash=request_hash,
        idempotency_key=key,
        reserved_cost=amount,
        state="QUEUED",
        sequence=0,
        actual_cost=Decimal("0"),
        checkpoint={"step": 0, "observations": [], "tokens": 0, "tool_calls": 0},
    )
    session.add(run)
    await session.flush()
    session.add(Outbox(tenant_id=identity.tenant_id, kind="run.admitted", resource_id=run.id))
    await emit(session, run, "run.queued", {"genome_hash": run.genome_hash})
    audit(session, identity, "run.admit", run.id)
    return run


def expired(run: Run, max_seconds: int) -> bool:
    return (datetime.now(UTC) - run.created_at.replace(tzinfo=UTC)).total_seconds() >= max_seconds
