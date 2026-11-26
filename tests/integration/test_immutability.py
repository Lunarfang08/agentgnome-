import os

import pytest
from agentgenome.auth import DEV_TENANT
from agentgenome.config import Settings
from agentgenome.db import Database
from conftest import TOKEN, published
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from apps.api.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("AG_TEST_POSTGRES") != "1", reason="requires real migrated PostgreSQL"
    ),
]


async def test_published_genome_and_terminal_run_reject_updates(manifest):
    db = Database(Settings().database_url)
    try:
        app = create_app(Settings(dev_auth=True, dev_token=TOKEN, fake_provider=True), db)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer " + TOKEN},
        ) as client:
            gid = await published(client, manifest)
            with pytest.raises(DBAPIError):
                async with db.session(DEV_TENANT) as session:
                    await session.execute(
                        text("UPDATE genomes SET version='9.9.9' WHERE id=:id"), {"id": gid}
                    )
            response = await client.post(
                "/api/v1/runs",
                json={"genome_id": gid, "task": "Cancel test"},
                headers={"Idempotency-Key": "immutable-" + gid},
            )
            assert response.status_code == 202
            rid = response.json()["id"]
            assert (await client.post(f"/api/v1/runs/{rid}/cancel")).status_code == 200
            with pytest.raises(DBAPIError):
                async with db.session(DEV_TENANT) as session:
                    await session.execute(
                        text("UPDATE runs SET state='RUNNING' WHERE id=:id"), {"id": rid}
                    )
    finally:
        await db.engine.dispose()
