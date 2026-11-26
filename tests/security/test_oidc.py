from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from agentgenome.auth import DEV_TENANT
from agentgenome.config import Settings
from agentgenome.db import Membership
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app


@pytest.mark.parametrize(
    "change,expected",
    [
        ({}, 200),
        ({"aud": "another-service"}, 401),
        ({"iss": "https://untrusted.example"}, 401),
        ({"exp": 1}, 401),
        ({"tenant_id": "other"}, 401),
    ],
)
async def test_oidc_signature_claims_and_membership(database, monkeypatch, change, expected):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        jwt.PyJWKClient,
        "get_signing_key_from_jwt",
        lambda self, token: SimpleNamespace(key=private.public_key()),
    )
    settings = Settings(
        _env_file=None,
        database_url=str(database.engine.url),
        oidc_issuer="https://identity.example",
        oidc_jwks_url="https://identity.example/jwks",
    )
    async with database.sessions() as session, session.begin():
        session.add(Membership(tenant_id=DEV_TENANT, subject="human", role="auditor"))
    claims = {
        "sub": "human",
        "iss": settings.oidc_issuer,
        "aud": settings.oidc_audience,
        "tenant_id": DEV_TENANT,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=1),
        **change,
    }
    token = jwt.encode(claims, private, algorithm="RS256", headers={"kid": "fixture-key"})
    app = create_app(settings, database)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        result = await client.get("/api/v1/me")
        assert result.status_code == expected
        if expected == 200:
            assert result.json()["scopes"] == ["read"]
            assert (await client.post("/api/v1/agents", json={"name": "denied"})).status_code == 403
