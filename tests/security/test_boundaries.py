import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from agentgenome.config import Settings
from agentgenome.db import ApiKey, Tenant, uid
from conftest import published
from sqlalchemy import select


@pytest.mark.parametrize(
    "config",
    [
        {"profile": "production", "dev_auth": True, "dev_token": "x" * 30},
        {"profile": "production", "fake_provider": True},
        {"profile": "production"},
        {"profile": "integration", "dev_auth": True, "dev_token": "x" * 30},
        {"dev_auth": True, "dev_token": "short"},
        {"dev_auth": True, "dev_token": "local-development-token-change-me"},
    ],
)
def test_unsafe_profiles_rejected(config):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **config)


async def test_no_auth(client):
    result = await client.get("/api/v1/agents", headers={"Authorization": ""})
    assert result.status_code == 401
    assert result.headers["content-type"].startswith("application/problem+json")
    assert "request_id" in result.json()


async def test_cross_tenant_and_scope(client, database, manifest):
    gid = await published(client, manifest)
    token = "ag_cross-tenant"
    async with database.sessions() as session, session.begin():
        tenant = Tenant(id=uid(), name="Other")
        session.add(tenant)
        await session.flush()
        session.add(
            ApiKey(
                tenant_id=tenant.id,
                digest=hashlib.sha256(token.encode()).hexdigest(),
                scopes=["read"],
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    headers = {"Authorization": "Bearer " + token}
    assert (await client.get(f"/api/v1/genomes/{gid}", headers=headers)).status_code == 404
    assert (
        await client.post("/api/v1/agents", json={"name": "bad"}, headers=headers)
    ).status_code == 403
    assert (await client.get("/api/v1/agents", headers=headers)).json()["items"] == []


async def test_api_key_one_time_and_revocation(client, database):
    result = await client.post("/api/v1/api-keys", json={"scopes": ["read"]})
    assert result.status_code == 201
    token = result.json()["token"]
    async with database.sessions() as session:
        key = await session.scalar(select(ApiKey).where(ApiKey.id == result.json()["id"]))
        assert key.digest != token
    assert (
        await client.get("/api/v1/me", headers={"Authorization": "Bearer " + token})
    ).status_code == 200
    assert (await client.post(f"/api/v1/api-keys/{result.json()['id']}/revoke")).status_code == 200
    assert (
        await client.get("/api/v1/me", headers={"Authorization": "Bearer " + token})
    ).status_code == 401


async def test_unimplemented_profiles_not_silently_executed(client, manifest):
    manifest["spec"]["sandbox"]["profile"] = "restricted-gvisor"
    gid = await published(client, manifest)
    result = await client.post(
        "/api/v1/runs",
        json={"genome_id": gid, "task": "no"},
        headers={"Idempotency-Key": "unsupported"},
    )
    assert result.status_code == 422


async def test_body_limit(client):
    response = await client.post(
        "/api/v1/agents", content=b"x" * 1048577, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


async def test_expired_api_key(client, database):
    token = "ag_expired-fixture"
    from agentgenome.auth import DEV_TENANT

    async with database.sessions() as session, session.begin():
        session.add(
            ApiKey(
                tenant_id=DEV_TENANT,
                digest=hashlib.sha256(token.encode()).hexdigest(),
                scopes=["read"],
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    assert (
        await client.get("/api/v1/me", headers={"Authorization": "Bearer " + token})
    ).status_code == 401


def test_configuration_errors_hide_secrets():
    secret = "private-key-never-print-this"
    with pytest.raises(ValueError) as error:
        Settings(_env_file=None, profile="production", provider_api_key=secret)
    assert secret not in str(error.value)
    settings = Settings(
        _env_file=None,
        provider_api_key=secret,
        database_url="postgresql+asyncpg://user:private-password@localhost/db",
    )
    assert secret not in repr(settings)
    assert "private-password" not in repr(settings)
