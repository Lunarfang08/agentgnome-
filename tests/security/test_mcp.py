import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from agentgenome.auth import DEV_TENANT
from agentgenome.config import Settings
from agentgenome.db import ApiKey, Tenant, uid
from agentgenome.mcp_server import MCPSettings, create_server
from conftest import published
from mcp import Client
from pydantic import ValidationError

from apps.api.main import create_app

TOKEN = "ag_mcp-test-scoped-key-1234567890123456"


async def scoped_server(database, scopes, tenant=DEV_TENANT):
    async with database.sessions() as session, session.begin():
        session.add(
            ApiKey(
                tenant_id=tenant,
                digest=hashlib.sha256(TOKEN.encode()).hexdigest(),
                scopes=scopes,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    app = create_app(Settings(_env_file=None, fake_provider=True), database)
    return create_server(MCPSettings(_env_file=None, api_token=TOKEN), httpx.ASGITransport(app=app))


async def test_mcp_publish_run_idempotency_and_cancel(database, manifest):
    server = await scoped_server(database, ["read", "write", "run"])
    async with Client(server, raise_exceptions=True) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert len(names) == 10
        assert not any("approv" in name or "api_key" in name for name in names)
        identity = await client.call_tool("get_identity", {})
        assert identity.structured_content["tenant_id"] == DEV_TENANT
        assert TOKEN not in str(identity)
        created = await client.call_tool("create_agent", {"name": "MCP fixture"})
        aid = created.structured_content["id"]
        genome = await client.call_tool("create_genome", {"agent_id": aid, "manifest": manifest})
        gid = genome.structured_content["id"]
        published_result = await client.call_tool("publish_genome", {"genome_id": gid})
        assert published_result.structured_content["digest"].startswith("sha256:")
        body = {
            "genome_id": gid,
            "task": "Approved fixture task",
            "idempotency_key": "mcp-stable-key",
        }
        first = await client.call_tool("start_run", body)
        second = await client.call_tool("start_run", body)
        rid = first.structured_content["id"]
        assert second.structured_content["id"] == rid
        conflict = await client.call_tool("start_run", {**body, "task": "Different task"})
        assert conflict.is_error and "409" in str(conflict.content)
        read = await client.call_tool("get_run", {"run_id": rid})
        assert read.structured_content["state"] == "QUEUED"
        cancelled = await client.call_tool("cancel_run", {"run_id": rid})
        assert cancelled.structured_content["state"] == "CANCELLED"


async def test_mcp_read_only_key_cannot_write(database):
    server = await scoped_server(database, ["read"])
    async with Client(server, raise_exceptions=True) as client:
        assert not (await client.call_tool("list_agents", {})).is_error
        denied = await client.call_tool("create_agent", {"name": "Forbidden"})
        assert denied.is_error and "403" in str(denied.content)
        invalid = await client.call_tool("get_run", {"run_id": "../../approvals"})
        assert invalid.is_error
        invalid_limit = await client.call_tool("list_agents", {"limit": 101})
        assert invalid_limit.is_error


async def test_mcp_cross_tenant_genome_is_denied(client, database, manifest):
    gid = await published(client, manifest)
    other = uid()
    async with database.sessions() as session, session.begin():
        session.add(Tenant(id=other, name="Other MCP tenant"))
    server = await scoped_server(database, ["read"], other)
    async with Client(server, raise_exceptions=True) as mcp:
        result = await mcp.call_tool("get_genome", {"genome_id": gid})
        assert result.is_error and "404" in str(result.content)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://example.com",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com/?token=secret",
    ],
)
def test_mcp_rejects_unsafe_api_urls(url):
    with pytest.raises(ValidationError):
        MCPSettings(_env_file=None, api_token=TOKEN, api_url=url)


def test_mcp_requires_scoped_secret_and_hides_it():
    with pytest.raises(ValidationError):
        MCPSettings(_env_file=None)
    secret = "human-development-token-must-not-appear"
    with pytest.raises(ValidationError) as error:
        MCPSettings(_env_file=None, api_token=secret)
    assert secret not in str(error.value)
    assert TOKEN not in repr(MCPSettings(_env_file=None, api_token=TOKEN))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"Location": "https://evil.example"}),
        httpx.Response(401, text=TOKEN),
        httpx.Response(200, text="x" * 2048),
        httpx.Response(200, text="not-json"),
    ],
)
async def test_mcp_bounds_errors_and_never_follows_redirects(response):
    calls = []

    def reply(request):
        calls.append(request)
        return response

    server = create_server(
        MCPSettings(_env_file=None, api_token=TOKEN, max_response_bytes=1024),
        httpx.MockTransport(reply),
    )
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool("get_identity", {})
        assert result.is_error and TOKEN not in str(result)
    assert len(calls) == 1


async def test_mcp_deadline_is_enforced():
    async def reply(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    server = create_server(
        MCPSettings(_env_file=None, api_token=TOKEN, timeout_seconds=0.01),
        httpx.MockTransport(reply),
    )
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool("get_identity", {})
        assert result.is_error and "timed out" in str(result.content)
