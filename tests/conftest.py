import json
from decimal import Decimal
from pathlib import Path

import pytest
from agentgenome.auth import DEV_TENANT, ROLES, Identity
from agentgenome.config import Settings
from agentgenome.db import Base, Database, Tenant
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app

TOKEN = "test-development-token-12345678"


@pytest.fixture
async def database(tmp_path):
    db = Database("sqlite+aiosqlite:///" + str(tmp_path / "test.db"))
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db.sessions() as session, session.begin():
        session.add(Tenant(id=DEV_TENANT, name="Test", budget=Decimal("5")))
    yield db
    await db.engine.dispose()


@pytest.fixture
def manifest():
    return json.loads(Path("examples/genomes/procurement.json").read_text())


@pytest.fixture
def who():
    return Identity("dev-admin", DEV_TENANT, frozenset(ROLES["admin"]))


@pytest.fixture
async def client(database):
    app = create_app(
        Settings(
            _env_file=None,
            dev_auth=True,
            dev_token=TOKEN,
            fake_provider=True,
            database_url=str(database.engine.url),
        ),
        database,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer " + TOKEN},
    ) as client:
        yield client


async def published(client, manifest):
    agent = await client.post("/api/v1/agents", json={"name": "Test"})
    assert agent.status_code == 201, agent.text
    genome = await client.post(f"/api/v1/agents/{agent.json()['id']}/genomes", json=manifest)
    assert genome.status_code == 201, genome.text
    gid = genome.json()["id"]
    result = await client.post(f"/api/v1/genomes/{gid}/publish")
    assert result.status_code == 200, result.text
    return gid
