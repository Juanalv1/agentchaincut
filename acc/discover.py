"""Tool discovery: read every tool the agent can call from its MCP servers (owner: P2)."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from world.servers import list_tools

_ROLE_BY_NAME = {
    "to": "destination", "cc": "destination", "bcc": "destination", "recipient": "destination",
    "email": "destination", "url": "destination", "webhook": "destination", "channel": "destination",
    "amount": "amount", "price": "amount", "total": "amount",
    "body": "content", "subject": "content", "message": "content", "text": "content",
    "content": "content", "note": "content", "comment": "content",
    "status": "filter", "query": "filter", "filter": "filter", "search": "filter",
}

_JSON_TYPES = ("string", "integer", "number", "boolean", "array", "object")


def arg_role(name: str) -> str:
    """Guess an argument's role from its name; object ids and destinations are attacker-controllable."""
    lowered = name.lower()
    if lowered in _ROLE_BY_NAME:
        return _ROLE_BY_NAME[lowered]
    if lowered.endswith("_id") or lowered == "id":
        return "object_id"
    if lowered.endswith(("_email", "_url", "_address")):
        return "destination"
    if lowered.endswith(("_amount", "_price")):
        return "amount"
    return "other"


def args_from_schema(input_schema: dict[str, Any]) -> list[dict[str, str]]:
    args = []
    for name, spec in (input_schema.get("properties") or {}).items():
        kind = spec.get("type", "string")
        if kind not in _JSON_TYPES:
            kind = "string"
        args.append({"name": name, "type": kind, "role": arg_role(name)})
    return args


async def discover(servers: dict[str, MCPServer]) -> list[dict[str, Any]]:
    """MCP `tools/list` on every server -> unclassified catalog entries (no legs yet)."""
    tools = await list_tools(servers)
    return [
        {
            "tool": t["tool"],
            "server": t["server"],
            "description": t["description"],
            "annotations": t["annotations"],
            "args": args_from_schema(t["input_schema"]),
        }
        for t in tools
    ]
