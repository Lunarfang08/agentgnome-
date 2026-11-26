from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AG_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    profile: Literal["dev", "integration", "production"] = "dev"
    database_url: str = Field(
        default="postgresql+asyncpg://agentgenome:local-development@localhost:55432/agentgenome",
        repr=False,
    )
    temporal_address: str = "127.0.0.1:7233"
    temporal_namespace: str = "default"
    task_queue: str = "agentgenome"
    redis_url: str = Field(default="redis://127.0.0.1:56379/0", repr=False)
    s3_endpoint: str = "http://127.0.0.1:9000"
    s3_access_key: SecretStr = SecretStr("local-development")
    s3_secret_key: SecretStr = SecretStr("local-development-secret")
    s3_bucket: str = "agentgenome"
    oidc_issuer: str = ""
    oidc_audience: str = "agentgenome"
    oidc_jwks_url: str = ""
    dev_auth: bool = False
    dev_token: SecretStr = SecretStr("")
    fake_provider: bool = False
    sandbox_profile: str = "trusted-fixture"
    sandbox_verified: bool = False
    tls_enabled: bool = False
    model_id: str = ""
    provider_api_key: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def safe_profile(self) -> "Settings":
        if self.dev_auth and (
            self.profile != "dev"
            or len(self.dev_token.get_secret_value()) < 24
            or self.dev_token.get_secret_value() == "local-development-token-change-me"
        ):
            raise ValueError(
                "development identity requires dev profile and a token of 24+ characters"
            )
        if self.fake_provider and self.profile == "production":
            raise ValueError("test provider is forbidden in production")
        if self.profile == "production":
            if not self.oidc_issuer.startswith("https://") or not self.oidc_jwks_url.startswith(
                "https://"
            ):
                raise ValueError("production requires HTTPS OIDC issuer and JWKS")
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("production requires PostgreSQL")
            # Fail closed until the authenticated hardened sandbox driver is implemented.
            raise ValueError(
                "production is blocked: verified hardened sandbox driver is not implemented"
            )
        return self
