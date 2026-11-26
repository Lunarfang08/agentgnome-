"""AgentGenome's local MCP server; every operation uses the authenticated control-plane API."""

import asyncio
import json
import sys
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentgenome.genome import Manifest


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AG_MCP_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
        validate_default=True,
    )
    api_url: str = "http://127.0.0.1:8080"
    api_token: SecretStr = SecretStr("")
    timeout_seconds: float = Field(default=15, gt=0, le=60)
    max_response_bytes: int = Field(default=2097152, ge=1024, le=8388608)

    @field_validator("api_url")
    @classmethod
    def trusted_endpoint(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("API URL must be an HTTP(S) origin without credentials, path or query")
        if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("non-loopback API connections require HTTPS")
        _ = url.port  # Validate the port before constructing an authenticated request.
        return value.rstrip("/")

    @field_validator("api_token")
    @classmethod
    def scoped_key(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if not token.startswith("ag_") or len(token) < 24:
            raise ValueError("use a scoped ag_ API key, never the human development token")
        return value


def create_server(
    settings: MCPSettings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> MCPServer[Any]:
    server: MCPServer[Any] = MCPServer(
        "AgentGenome",
        instructions=(
            "Manage AgentGenome through its authorized API. Published genomes are immutable. "
            "Run admission remains subject to supported routes and tenant budgets. "
            "Human approvals must be performed in the studio; no approval tool is exposed."
        ),
    )
    read = ToolAnnotations(read_only_hint=True, open_world_hint=False)
    write = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
    idempotent = ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    )

    async def request(
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": "Bearer " + settings.api_token.get_secret_value()}
        if key is not None:
            headers["Idempotency-Key"] = key
        try:
            async with (
                asyncio.timeout(settings.timeout_seconds),
                httpx.AsyncClient(
                    timeout=settings.timeout_seconds,
                    follow_redirects=False,
                    trust_env=False,
                    transport=transport,
                ) as client,
                client.stream(
                    method,
                    settings.api_url + "/api/v1" + path,
                    headers=headers,
                    json=body,
                    params=params,
                ) as response,
            ):
                if not 200 <= response.status_code < 300:
                    raise ToolError(
                        f"AgentGenome API rejected the request ({response.status_code})"
                    )
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > settings.max_response_bytes:
                        raise ToolError(
                            "API response exceeds the MCP size limit; request less data"
                        )
                    data.extend(chunk)
                result = json.loads(data)
                if not isinstance(result, dict):
                    raise ToolError("AgentGenome API returned an invalid response")
                return result
        except (httpx.RequestError, TimeoutError):
            raise ToolError("AgentGenome API is unavailable or the request timed out") from None
        except (ValueError, UnicodeError):
            raise ToolError("AgentGenome API returned invalid JSON") from None

    @server.tool(annotations=read)
    async def get_identity() -> dict[str, Any]:
        """Get the current service identity, tenant and granted API scopes. Never returns tokens."""
        return await request("GET", "/me")

    @server.tool(annotations=read)
    async def list_agents(
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
        cursor: UUID | None = None,
    ) -> dict[str, Any]:
        """List agents visible to this identity; pass next_cursor to read the next page."""
        return await request(
            "GET", "/agents", params={"limit": limit, "cursor": str(cursor) if cursor else ""}
        )

    @server.tool(annotations=write)
    async def create_agent(
        name: Annotated[str, Field(min_length=1, max_length=100)],
    ) -> dict[str, Any]:
        """Register an agent. Requires write scope; does not publish or run a genome."""
        return await request("POST", "/agents", body={"name": name})

    @server.tool(annotations=write)
    async def create_genome(agent_id: UUID, manifest: Manifest) -> dict[str, Any]:
        """Create a validated genome draft for an agent. Requires write scope."""
        return await request(
            "POST", f"/agents/{agent_id}/genomes", body=manifest.model_dump(mode="json")
        )

    @server.tool(annotations=idempotent)
    async def publish_genome(genome_id: UUID) -> dict[str, Any]:
        """Publish an immutable genome snapshot. Requires write scope."""
        return await request("POST", f"/genomes/{genome_id}/publish")

    @server.tool(annotations=read)
    async def get_genome(genome_id: UUID) -> dict[str, Any]:
        """Read an authorized genome manifest and its publication/hash metadata."""
        return await request("GET", f"/genomes/{genome_id}")

    @server.tool(annotations=read)
    async def list_runs(
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
        cursor: UUID | None = None,
    ) -> dict[str, Any]:
        """List authorized runs with cursor pagination."""
        return await request(
            "GET", "/runs", params={"limit": limit, "cursor": str(cursor) if cursor else ""}
        )

    @server.tool(annotations=read)
    async def get_run(run_id: UUID) -> dict[str, Any]:
        """Read a run's state, checkpoint, pinned genome hash and terminal result."""
        return await request("GET", f"/runs/{run_id}")

    @server.tool(annotations=idempotent)
    async def start_run(
        genome_id: UUID,
        task: Annotated[str, Field(min_length=1, max_length=10000)],
        idempotency_key: Annotated[str, Field(min_length=1, max_length=128)],
    ) -> dict[str, Any]:
        """Admit a run using a published genome. Requires run scope. Reuse the key only for retries
        of this exact request. Execution remains subject to budgets, policy and human approval.
        """
        return await request(
            "POST", "/runs", body={"genome_id": str(genome_id), "task": task}, key=idempotency_key
        )

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    async def cancel_run(run_id: UUID) -> dict[str, Any]:
        """Cancel an authorized run. Requires run scope. Does not undo committed side effects."""
        return await request("POST", f"/runs/{run_id}/cancel")

    return server


def main() -> None:
    try:
        settings = MCPSettings()
    except ValueError:
        print(
            "Configure AG_MCP_API_URL and a scoped AG_MCP_API_TOKEN; see README.", file=sys.stderr
        )
        raise SystemExit(2) from None
    # Stdout is exclusively the MCP protocol; configuration and failures never print credentials.
    create_server(settings).run(transport="stdio")


if __name__ == "__main__":
    main()
