"""Real database tests; never silently replace PostgreSQL with SQLite."""

import asyncio
import hashlib
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from agentgenome.auth import DEV_TENANT
from agentgenome.config import Settings
from agentgenome.db import Agent, ApiKey, Database, Tenant, uid
from conftest import published
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from apps.api.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("AG_TEST_POSTGRES") != "1", reason="set AG_TEST_POSTGRES=1 after real migrations"
    ),
]


async def test_rls_and_pool_context():
    db = Database(Settings().database_url)
    try:
        async with db.sessions() as session, session.begin():
            tenant = Tenant(id=uid(), name="RLS test")
            session.add(tenant)
            await session.flush()
            tenant_id = tenant.id
        async with db.session(tenant_id) as session:
            agent = Agent(tenant_id=tenant_id, name="Private")
            session.add(agent)
            await session.flush()
            agent_id = agent.id
        async with db.session(DEV_TENANT) as session:
            assert await session.get(Agent, agent_id) is None
        async with db.sessions() as session:
            assert await session.get(Agent, agent_id) is None
        async with db.session(tenant_id) as session:
            assert await session.get(Agent, agent_id) is not None
        async with db.sessions() as session:
            role = (
                await session.execute(
                    text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
                )
            ).one()
            assert role == (False, False)
    finally:
        await db.engine.dispose()


async def test_atomic_concurrent_admission(manifest):
    db = Database(Settings().database_url)
    settings = Settings(fake_provider=True)
    token = "ag_" + uid()
    tenant_id = uid()
    app = create_app(settings, db)
    try:
        async with db.sessions() as session, session.begin():
            tenant = Tenant(id=tenant_id, name="Concurrent test", budget=Decimal("2"))
            session.add(tenant)
            await session.flush()
            session.add(
                ApiKey(
                    tenant_id=tenant_id,
                    digest=hashlib.sha256(token.encode()).hexdigest(),
                    scopes=["read", "write", "run"],
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer " + token},
        ) as client:
            gid = await published(client, manifest)
            responses = await asyncio.gather(
                *[
                    client.post(
                        "/api/v1/runs",
                        json={"genome_id": gid, "task": "Concurrent fixture"},
                        headers={"Idempotency-Key": "parallel-" + uid()},
                    )
                    for _ in range(8)
                ]
            )
            assert [r.status_code for r in responses].count(202) == 2
            assert [r.status_code for r in responses].count(429) == 6
            for result in responses:
                if result.status_code == 202:
                    await client.post(f"/api/v1/runs/{result.json()['id']}/cancel")
        async with db.sessions() as session, session.begin():
            tenant = await session.get(Tenant, tenant_id)
            assert tenant.reserved == 0
            tenant.budget = Decimal("100")
    finally:
        await db.engine.dispose()
