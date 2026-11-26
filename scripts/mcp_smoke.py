"""Exercise the real local stdio server against the running authenticated AgentGenome API."""

import asyncio
import json
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters


async def main(config):
    server = config["mcpServers"]["agentgenome"]
    parameters = StdioServerParameters(command=server["command"], env=server["env"])
    async with Client(parameters) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert len(names) == 10 and "approve" not in names
        identity = await client.call_tool("get_identity", {})
        assert not identity.is_error, identity.content
        scopes = identity.structured_content["scopes"]
        assert "approve" not in scopes and "admin" not in scopes
        agents = await client.call_tool("list_agents", {"limit": 1})
        assert not agents.is_error, agents.content
        print(
            json.dumps(
                {
                    "server": "AgentGenome",
                    "transport": "stdio",
                    "tools": len(names),
                    "scopes": scopes,
                    "api_roundtrip": "passed",
                }
            )
        )


if __name__ == "__main__":
    path = Path(__file__).resolve().parents[1] / ".local/mcp.json"
    if not path.exists():
        raise SystemExit("Run make mcp-config with the API running first")
    asyncio.run(main(json.loads(path.read_text())))
