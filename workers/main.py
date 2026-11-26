import asyncio
from datetime import timedelta

from agentgenome.config import Settings
from agentgenome.db import Database, Outbox, Run, Tenant
from agentgenome.runtime import advance
from agentgenome.service import finish, scoped
from sqlalchemy import select
from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker

from workers.workflows import AgentWorkflow


async def main() -> None:
    settings = Settings()
    if not settings.fake_provider:
        raise RuntimeError(
            "This worker currently supports only explicitly enabled fixture execution"
        )
    database = Database(settings.database_url)
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)

    @activity.defn(name="advance_run")
    async def advance_run(run_id: str, tenant_id: str) -> str:
        return await advance(database, run_id, tenant_id)

    @activity.defn(name="cancel_run")
    async def cancel_run(run_id: str, tenant_id: str) -> str:
        async with database.session(tenant_id) as session:
            run = await scoped(session, Run, run_id, tenant_id, lock=True)
            await finish(session, run, "CANCELLED", {"code": "cancelled"})
            return run.state

    async def dispatch() -> None:
        while True:
            async with database.sessions() as catalog:
                tenants = list(await catalog.scalars(select(Tenant.id)))
            for tenant_id in tenants:
                async with database.session(tenant_id) as session:
                    pending = list(
                        await session.scalars(
                            select(Outbox)
                            .where(
                                Outbox.tenant_id == tenant_id,
                                Outbox.delivered.is_(False),
                                Outbox.attempts < 10,
                            )
                            .with_for_update(skip_locked=True)
                            .limit(20)
                        )
                    )
                    for item in pending:
                        item.attempts += 1
                        try:
                            await client.start_workflow(
                                AgentWorkflow.run,
                                args=[item.resource_id, tenant_id],
                                id="run-" + item.resource_id,
                                task_queue=settings.task_queue,
                                execution_timeout=timedelta(days=2),
                            )
                        except WorkflowAlreadyStartedError:
                            pass
                        except Exception:
                            if item.attempts >= 10:
                                run = await scoped(
                                    session, Run, item.resource_id, tenant_id, lock=True
                                )
                                await finish(
                                    session, run, "FAILED", {"code": "workflow_dispatch_failed"}
                                )
                            continue
                        item.delivered = True
            await asyncio.sleep(1)

    try:
        async with Worker(
            client,
            task_queue=settings.task_queue,
            workflows=[AgentWorkflow],
            activities=[advance_run, cancel_run],
        ):
            await dispatch()
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
