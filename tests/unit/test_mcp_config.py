import json
from pathlib import Path

import httpx

from scripts.mcp_config import configure


def test_config_is_private_and_rotation_revokes_previous_key(tmp_path):
    old_id = "00000000-0000-4000-8000-000000000002"
    old = "ag_" + "o" * 40
    new = "ag_" + "n" * 40
    calls = []

    def respond(request):
        calls.append(request)
        if request.url.path == "/api/v1/me":
            assert request.headers["Authorization"] == "Bearer " + old
            return httpx.Response(200, json={"subject": old_id})
        if request.url.path == "/api/v1/api-keys":
            body = json.loads(request.content)
            assert body["scopes"] == ["read", "write", "run"]
            assert body["expires_in_hours"] == 24
            return httpx.Response(201, json={"id": "new-key", "token": new})
        assert request.url.path == f"/api/v1/api-keys/{old_id}/revoke"
        assert request.headers["Authorization"] == "Bearer human-owner"
        return httpx.Response(200, json={"revoked": True})

    target = tmp_path / "mcp.json"
    target.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "agentgenome": {
                        "env": {"AG_MCP_API_URL": "http://127.0.0.1:8080", "AG_MCP_API_TOKEN": old}
                    }
                }
            }
        )
    )
    with httpx.Client(
        base_url="http://127.0.0.1:8080",
        headers={"Authorization": "Bearer human-owner"},
        transport=httpx.MockTransport(respond),
    ) as client:
        configure(client, target, Path("/example/agentgenome-mcp"))
    saved = json.loads(target.read_text())["mcpServers"]["agentgenome"]
    assert saved["env"]["AG_MCP_API_TOKEN"] == new
    assert saved["command"] == "/example/agentgenome-mcp"
    assert len(calls) == 3
    assert target.stat().st_mode & 0o077 == 0
