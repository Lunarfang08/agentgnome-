import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from fastapi import HTTPException
from sqlalchemy import select

from agentgenome.config import Settings
from agentgenome.db import ApiKey, Database, Membership

DEV_TENANT = "00000000-0000-4000-8000-000000000001"
ROLES = {
    "admin": {"read", "write", "run", "approve", "admin"},
    "developer": {"read", "write", "run"},
    "auditor": {"read"},
    "approver": {"read", "approve"},
}


@dataclass(frozen=True)
class Identity:
    subject: str
    tenant_id: str
    scopes: frozenset[str]

    def require(self, scope: str) -> None:
        if scope not in self.scopes:
            raise HTTPException(403, "insufficient scope")


class Authenticator:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database
        self.jwks = (
            jwt.PyJWKClient(settings.oidc_jwks_url, lifespan=300)
            if settings.oidc_jwks_url
            else None
        )

    async def authenticate(self, token: str) -> Identity:
        s = self.settings
        if s.dev_auth and secrets.compare_digest(token, s.dev_token.get_secret_value()):
            return Identity("dev-admin", DEV_TENANT, frozenset(ROLES["admin"]))
        async with self.database.sessions() as session:
            if token.startswith("ag_"):
                key = await session.scalar(
                    select(ApiKey).where(
                        ApiKey.digest == hashlib.sha256(token.encode()).hexdigest(),
                        ApiKey.revoked.is_(False),
                    )
                )
                if key and key.expires_at.replace(tzinfo=UTC) > datetime.now(UTC):
                    return Identity(key.id, key.tenant_id, frozenset(key.scopes))
                raise HTTPException(401, "invalid credentials")
            if self.jwks is None:
                raise HTTPException(401, "invalid credentials")
            import asyncio

            try:
                signing_key = await asyncio.to_thread(self.jwks.get_signing_key_from_jwt, token)
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=s.oidc_audience,
                    issuer=s.oidc_issuer,
                    options={"require": ["exp", "iat", "sub", "iss", "aud"]},
                )
                membership = await session.scalar(
                    select(Membership).where(
                        Membership.subject == claims["sub"],
                        Membership.tenant_id == claims.get("tenant_id"),
                    )
                )
                if membership:
                    return Identity(
                        claims["sub"],
                        membership.tenant_id,
                        frozenset(ROLES.get(membership.role, set())),
                    )
            except (jwt.PyJWTError, ValueError, KeyError):
                pass
        raise HTTPException(401, "invalid credentials")
