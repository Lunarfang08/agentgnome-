"""Create a private MCP client configuration using a limited, expiring service API key."""

import json
import os
import sys
import tempfile
from pathlib import Path
from uuid import UUID

import httpx
from agentgenome.config import Settings
from agentgenome.mcp_server import MCPSettings


def configure(client: httpx.Client, target: Path, command: Path) -> None:
    origin = str(client.base_url).rstrip("/")
    old_id = None
    if target.exists():
        old = json.loads(target.read_text())["mcpServers"]["agentgenome"]["env"]
        if old.get("AG_MCP_API_URL") == origin:
            response = client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + old["AG_MCP_API_TOKEN"]}
            )
            if response.is_success:
                old_id = str(UUID(response.json()["subject"]))
    response = client.post(
        "/api/v1/api-keys", json={"scopes": ["read", "write", "run"], "expires_in_hours": 24}
    )
    response.raise_for_status()
    key = response.json()
    settings = MCPSettings(_env_file=None, api_url=origin, api_token=key["token"])
    config = {
        "mcpServers": {
            "agentgenome": {
                "command": str(command),
                "env": {
                    "AG_MCP_API_URL": settings.api_url,
                    "AG_MCP_API_TOKEN": settings.api_token.get_secret_value(),
                },
            }
        }
    }
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix="mcp-", dir=target.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(config, output, indent=2)
            output.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    except BaseException:
        client.post(f"/api/v1/api-keys/{key['id']}/revoke").raise_for_status()
        raise
    finally:
        Path(temporary).unlink(missing_ok=True)
    if old_id is not None:
        client.post(f"/api/v1/api-keys/{old_id}/revoke").raise_for_status()


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    settings = Settings()
    if settings.profile != "dev" or not settings.dev_auth:
        raise SystemExit("Automatic MCP setup requires the explicit local development identity")
    command = Path(sys.executable).parent / (
        "agentgenome-mcp.exe" if os.name == "nt" else "agentgenome-mcp"
    )
    if not command.exists():
        raise SystemExit("Install the current project first: uv sync --frozen")
    target = root / ".local/mcp.json"
    try:
        with httpx.Client(
            base_url="http://127.0.0.1:8080",
            timeout=10,
            follow_redirects=False,
            headers={"Authorization": "Bearer " + settings.dev_token.get_secret_value()},
        ) as client:
            configure(client, target, command)
    except (httpx.HTTPError, ValueError, OSError, KeyError):
        raise SystemExit(
            "MCP setup failed. Check the API and local credentials. No secrets were printed."
        ) from None
    print("Private MCP config: .local/mcp.json (24-hour key; no approval/admin scope).")
