"""MCP servers (tickets, billing, mail) over the in-memory `World` backend.

Each server is built with the backend service credential; only the proxy holds the server
objects, so the agent cannot reach the backend without going through the policy engine.

Run one server over stdio: `python -m world.servers billing --seed 26`.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from world.data import AGENT_ID, World, WorldError

TOOL_NAMES = (
    "tickets.get",
    "tickets.add_note",
    "billing.invoice_read",
    "billing.invoice_list",
    "billing.invoice_list_all",
    "billing.refund",
    "mail.send",
)


def build_servers(world: World, credential: str) -> dict[str, MCPServer]:
    """Return {server name: MCPServer}. Raises PermissionError on a wrong credential."""
    if credential != world.service_key:
        raise PermissionError("invalid backend service credential")

    tickets = MCPServer("tickets", instructions="Support tickets backend.")
    billing = MCPServer("billing", instructions="Billing backend: invoices and refunds.")
    mail = MCPServer("mail", instructions="Outbound email.")

    @tickets.tool(
        name="get",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    def ticket_get(ticket_id: str) -> dict[str, Any]:
        """Read a support ticket, including the customer's free-text message."""
        return world.get_ticket(ticket_id)

    @tickets.tool(
        name="add_note",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False),
    )
    def ticket_add_note(ticket_id: str, body: str, author: str = AGENT_ID) -> dict[str, Any]:
        """Append a note to a ticket; notes are visible to the customer."""
        return world.add_note(ticket_id, body, author)

    @billing.tool(name="invoice_read", annotations=ToolAnnotations(read_only_hint=True))
    def invoice_read(invoice_id: str) -> dict[str, Any]:
        """Read one invoice by id."""
        return world.invoice_read(invoice_id)

    @billing.tool(name="invoice_list", annotations=ToolAnnotations(read_only_hint=True))
    def invoice_list(customer_id: str) -> dict[str, Any]:
        """List the invoices of one customer."""
        return {"invoices": world.invoice_list(customer_id)}

    @billing.tool(name="invoice_list_all", annotations=ToolAnnotations(read_only_hint=True))
    def invoice_list_all(status: str = "any") -> dict[str, Any]:
        """List invoices across all customers."""
        return {"invoices": world.invoice_list_all(status)}

    @billing.tool(
        name="refund",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
    )
    def refund(invoice_id: str, amount: float, currency: str) -> dict[str, Any]:
        """Refund an invoice, fully or partially."""
        return world.refund(invoice_id, amount, currency)

    @mail.tool(
        name="send",
        annotations=ToolAnnotations(read_only_hint=False, open_world_hint=True),
    )
    def mail_send(to: str, subject: str, body: str) -> dict[str, Any]:
        """Send an email to any address."""
        return world.send_mail(to, subject, body)

    return {"tickets": tickets, "billing": billing, "mail": mail}


def split_tool_name(tool: str) -> tuple[str, str]:
    server, _, name = tool.partition(".")
    if not server or not name:
        raise ValueError(f"tool name must be <server>.<tool>, got {tool!r}")
    return server, name


async def list_tools(servers: dict[str, MCPServer]) -> list[dict[str, Any]]:
    """MCP `tools/list` across servers, flattened to qualified names (`billing.refund`)."""
    out: list[dict[str, Any]] = []
    for server_name, server in servers.items():
        for tool in await server.list_tools():
            annotations = tool.annotations.model_dump(by_alias=True, exclude_none=True) if tool.annotations else {}
            out.append(
                {
                    "tool": f"{server_name}.{tool.name}",
                    "server": server_name,
                    "description": tool.description or "",
                    "annotations": annotations,
                    "input_schema": tool.input_schema,
                }
            )
    return out


async def call_tool(servers: dict[str, MCPServer], tool: str, args: dict[str, Any]) -> Any:
    """MCP `tools/call` by qualified name; returns the decoded JSON result.

    Raises WorldError for backend failures and KeyError for an unknown server.
    """
    server_name, name = split_tool_name(tool)
    server = servers[server_name]
    try:
        result = await server.call_tool(name, args)
    except Exception as exc:  # unwrap the backend error the tool raised
        cause: BaseException | None = exc
        while cause is not None:
            if isinstance(cause, WorldError):
                raise cause from exc
            cause = cause.__cause__
        # argument validation and other tool failures go back to the caller as a tool error
        raise WorldError(f"{tool} failed: {exc}") from exc
    if getattr(result, "is_error", False):
        raise WorldError(_text_of(result))
    text = _text_of(result)
    return json.loads(text) if text else None


def _text_of(result: Any) -> str:
    return "".join(getattr(block, "text", "") for block in getattr(result, "content", []))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run one world MCP server over stdio")
    parser.add_argument("server", choices=["tickets", "billing", "mail"])
    parser.add_argument("--seed", type=int, default=26)
    args = parser.parse_args(argv)
    world = World(seed=args.seed)
    build_servers(world, world.service_key)[args.server].run("stdio")


if __name__ == "__main__":
    main()
