from agentgenome.db import Approval, SimOrder, Tenant
from agentgenome.runtime import advance
from conftest import published
from sqlalchemy import func, select


async def start(client, manifest, key="run-1"):
    gid = await published(client, manifest)
    result = await client.post(
        "/api/v1/runs",
        json={"genome_id": gid, "task": "Order paper"},
        headers={"Idempotency-Key": key},
    )
    assert result.status_code == 202, result.text
    return result.json()["id"], gid


async def test_approval_reconciliation_checkpoint_and_sse(client, database, manifest, who):
    rid, gid = await start(client, manifest)
    assert await advance(database, rid, who.tenant_id) == "RUNNING"
    assert await advance(database, rid, who.tenant_id) == "RUNNING"
    assert await advance(database, rid, who.tenant_id) == "WAITING_APPROVAL"
    approval = (await client.get("/api/v1/approvals")).json()["items"][0]
    approved = await client.post(f"/api/v1/approvals/{approval['id']}/approve")
    assert approved.status_code == 200
    replay = await client.post(f"/api/v1/approvals/{approval['id']}/approve")
    assert replay.status_code == 409
    assert await advance(database, rid, who.tenant_id, fault_after_commit=True) == "RUNNING"
    # A new engine simulates a restarted activity process, reading durable state.
    from agentgenome.db import Database

    recovered = Database(str(database.engine.url))
    try:
        assert await advance(recovered, rid, who.tenant_id) == "RUNNING"
        assert await advance(recovered, rid, who.tenant_id) == "SUCCEEDED"
        assert await advance(recovered, rid, who.tenant_id) == "SUCCEEDED"
    finally:
        await recovered.engine.dispose()
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(SimOrder)) == 1
        tenant = await session.get(Tenant, who.tenant_id)
        assert tenant.reserved == 0
    events = await client.get(f"/api/v1/runs/{rid}/events", headers={"Last-Event-ID": "2"})
    assert events.status_code == 200
    assert "id: 1\n" not in events.text
    assert "tool.reconciled" in events.text
    assert "run.succeeded" in events.text
    sequences = [int(line[4:]) for line in events.text.splitlines() if line.startswith("id: ")]
    assert sequences == list(range(3, max(sequences) + 1))


async def test_idempotency_and_budget(client, database, manifest, who):
    rid, gid = await start(client, manifest)
    body = {"genome_id": gid, "task": "Order paper"}
    again = await client.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "run-1"})
    assert again.json()["id"] == rid
    conflict = await client.post(
        "/api/v1/runs", json={**body, "task": "Different"}, headers={"Idempotency-Key": "run-1"}
    )
    assert conflict.status_code == 409
    for n in range(4):
        assert (
            await client.post("/api/v1/runs", json=body, headers={"Idempotency-Key": f"other-{n}"})
        ).status_code == 202
    denied = await client.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "exhausted"})
    assert denied.status_code == 429
    assert (await client.post(f"/api/v1/runs/{rid}/cancel")).json()["state"] == "CANCELLED"
    assert await advance(database, rid, who.tenant_id) == "CANCELLED"
    assert (
        await client.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "after-release"})
    ).status_code == 202


async def test_denied_tool(client, database, manifest, who):
    manifest["spec"]["tools"]["allowed"] = ["orders.submit"]
    rid, _ = await start(client, manifest)
    assert await advance(database, rid, who.tenant_id) == "FAILED"
    result = (await client.get(f"/api/v1/runs/{rid}")).json()
    assert result["result"]["code"] == "tool_denied"


async def test_expired_approval(client, database, manifest, who):
    from datetime import UTC, datetime, timedelta

    rid, _ = await start(client, manifest)
    for _ in range(3):
        await advance(database, rid, who.tenant_id)
    async with database.sessions() as session, session.begin():
        approval = await session.scalar(select(Approval).where(Approval.run_id == rid))
        approval.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await advance(database, rid, who.tenant_id) == "FAILED"


async def test_token_limit_prevents_effect(client, database, manifest, who):
    manifest["spec"]["limits"]["maxTotalTokens"] = 1
    rid, _ = await start(client, manifest)
    assert await advance(database, rid, who.tenant_id) == "BUDGET_EXHAUSTED"


async def test_tampered_approval_stops_write(client, database, manifest, who):
    rid, _ = await start(client, manifest)
    for _ in range(3):
        await advance(database, rid, who.tenant_id)
    async with database.sessions() as session, session.begin():
        approval = await session.scalar(select(Approval).where(Approval.run_id == rid))
        approval.status = "APPROVED"
        approval.arguments_hash = "0" * 64
    assert await advance(database, rid, who.tenant_id) == "FAILED"
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(SimOrder)) == 0
