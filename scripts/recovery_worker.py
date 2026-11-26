"""Test-only Temporal worker: pause after a committed simulated order, then crash externally."""

import asyncio
import sys

from agentgenome.config import Settings
from agentgenome.db import Database, Run, ToolAction
from agentgenome.runtime import advance
from agentgenome.service import finish, scoped
from sqlalchemy import select
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

from workers.workflows import AgentWorkflow


async def main():
    target, tenant, queue, mode = sys.argv[1:]
    settings = Settings()
    if settings.profile != "dev" or not settings.fake_provider:
        raise RuntimeError("Recovery fixture is restricted to explicit development profile")
    db = Database(settings.database_url)
    client = await Client.connect(settings.temporal_address)

    @activity.defn(name="advance_run")
    async def advance_run(run_id: str, tenant_id: str) -> str:
        if (run_id, tenant_id) != (target, tenant):
            raise ValueError("unexpected test workload")
        state = await advance(db, run_id, tenant_id, fault_after_commit=mode == "crash")
        if mode == "crash":
            async with db.session(tenant) as session:
                unknown = await session.scalar(
                    select(ToolAction).where(
                        ToolAction.run_id == target, ToolAction.state == "UNKNOWN"
                    )
                )
            if unknown:
                await asyncio.sleep(60)  # Killed by the test after verifying the committed order.
        return state

    @activity.defn(name="cancel_run")
    async def cancel_run(run_id: str, tenant_id: str) -> str:
        if (run_id, tenant_id) != (target, tenant):
            raise ValueError("unexpected test workload")
        async with db.session(tenant) as session:
            run = await scoped(session, Run, run_id, tenant, lock=True)
            await finish(session, run, "CANCELLED", {"code": "cancelled"})
            return run.state

    async with Worker(
        client, task_queue=queue, workflows=[AgentWorkflow], activities=[advance_run, cancel_run]
    ):
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
