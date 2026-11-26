"""Requires local API/Temporal/PostgreSQL and no ordinary dispatch worker during admission."""

import asyncio
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
from agentgenome.auth import DEV_TENANT
from agentgenome.config import Settings
from agentgenome.db import Database, Outbox, SimOrder, ToolAction
from sqlalchemy import func, select
from temporalio.client import Client

from workers.workflows import AgentWorkflow


async def main(manifest, log):
    settings = Settings()
    if settings.profile != "dev" or not settings.dev_auth:
        raise RuntimeError("Explicit development profile required")
    db = Database(settings.database_url)
    queue = "recovery-" + uuid.uuid4().hex
    worker = None
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:8080/api/v1",
            timeout=10,
            headers={"Authorization": "Bearer " + settings.dev_token.get_secret_value()},
        ) as api:

            async def post(path, body=None, **kwargs):
                response = await api.post(path, json=body, **kwargs)
                response.raise_for_status()
                return response.json()

            agent = await post("/agents", {"name": "Worker recovery fixture"})
            genome = await post(f"/agents/{agent['id']}/genomes", manifest)
            await post(f"/genomes/{genome['id']}/publish")
            run = await post(
                "/runs",
                {"genome_id": genome["id"], "task": "Recover committed fixture order"},
                headers={"Idempotency-Key": queue},
            )
            rid = run["id"]
            async with db.session(DEV_TENANT) as session:
                outbox = await session.scalar(select(Outbox).where(Outbox.resource_id == rid))
                outbox.delivered = True
            client = await Client.connect(settings.temporal_address)
            await client.start_workflow(
                AgentWorkflow.run, args=[rid, DEV_TENANT], id="run-" + rid, task_queue=queue
            )

            def launch(mode):
                return subprocess.Popen(
                    [sys.executable, "scripts/recovery_worker.py", rid, DEV_TENANT, queue, mode],
                    stdout=log,
                    stderr=log,
                )

            worker = launch("crash")
            approved = False
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                pending = await api.get("/approvals")
                pending.raise_for_status()
                if not approved:
                    match = next((a for a in pending.json()["items"] if a["run_id"] == rid), None)
                    if match:
                        await post(f"/approvals/{match['id']}/approve")
                        approved = True
                async with db.session(DEV_TENANT) as session:
                    unknown = await session.scalar(
                        select(ToolAction).where(
                            ToolAction.run_id == rid, ToolAction.state == "UNKNOWN"
                        )
                    )
                if unknown:
                    worker.kill()
                    worker.wait(timeout=10)
                    break
                await asyncio.sleep(0.2)
            else:
                raise TimeoutError(
                    "No committed-unknown action observed; inspect recovery worker log"
                )
            worker = launch("recover")
            deadline = time.monotonic() + 70
            while time.monotonic() < deadline:
                response = await api.get(f"/runs/{rid}")
                response.raise_for_status()
                if response.json()["state"] == "SUCCEEDED":
                    break
                await asyncio.sleep(0.5)
            else:
                raise TimeoutError("Workflow did not recover after worker termination")
            async with db.session(DEV_TENANT) as session:
                count = await session.scalar(
                    select(func.count())
                    .select_from(SimOrder)
                    .where(SimOrder.tenant_id == DEV_TENANT, SimOrder.run_id == rid)
                )
                action = await session.scalar(
                    select(ToolAction).where(
                        ToolAction.run_id == rid, ToolAction.tool == "orders.submit"
                    )
                )
                assert count == 1 and action.state == "RECONCILED"
            print(
                json.dumps(
                    {
                        "run_id": rid,
                        "state": "SUCCEEDED",
                        "orders": count,
                        "action_state": "RECONCILED",
                        "worker_killed": True,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                    }
                )
            )
    finally:
        if worker is not None and worker.poll() is None:
            worker.terminate()
            worker.wait(timeout=10)
        await db.engine.dispose()


if __name__ == "__main__":
    with open("/tmp/agentgenome-recovery-worker.log", "w") as log:
        asyncio.run(main(json.loads(Path("examples/genomes/procurement.json").read_text()), log))
