"""Credential-holding MCP proxy (owner: P1).

Only the proxy holds the backend MCP servers (built with the service credential); the agent
talks MCP to the proxy. Each session is bound to one ticket and its trusted context is
fetched by the proxy from the backend, never taken from agent text. Every `tools/call` goes
through the shared policy engine, is appended to the hash-chained ledger and published as an
event (the API relays events over SSE). Unknown sessions, unknown tools and engine errors deny.
"""

from __future__ import annotations

import itertools
import json
import time
from typing import Any, Callable

import mcp_types as types
from mcp.server.lowlevel import Server

from acc.policy_engine import DEFAULT_AGENT, Decision, check
from proxy.ledger import Ledger
from world.data import World, WorldError
from world.servers import build_servers, call_tool, list_tools

Listener = Callable[[dict[str, Any]], None]


def to_mcp_name(tool: str) -> str:
    """`billing.invoice_read` -> `billing__invoice_read` (API tool names cannot contain dots)."""
    return tool.replace(".", "__", 1)


def from_mcp_name(name: str) -> str:
    return name.replace("__", ".", 1)


class Proxy:
    def __init__(self, world: World, credential: str, policy: dict[str, Any], ledger: Ledger,
                 agent: str = DEFAULT_AGENT) -> None:
        self._servers = build_servers(world, credential)  # raises PermissionError on a bad key
        self._backend = world
        self.policy = policy
        self.ledger = ledger
        self.agent = agent
        self.sessions: dict[str, dict[str, Any]] = {}
        self.pending: dict[str, dict[str, Any]] = {}
        self._listeners: list[Listener] = []
        self._ids = itertools.count(1)
        self._tool_specs: list[dict[str, Any]] | None = None

    # -- events -------------------------------------------------------------------------------

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _publish(self, event: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:  # a broken subscriber must never affect enforcement
                pass

    # -- sessions -----------------------------------------------------------------------------

    def start_session(self, ticket_id: str, session_id: str | None = None) -> str:
        context, _ = self._backend.trusted_context(ticket_id)
        sid = session_id or f"s-live-{next(self._ids)}"
        self.sessions[sid] = context
        self._publish({"type": "session", "session_id": sid, "ticket_id": ticket_id})
        return sid

    # -- calls --------------------------------------------------------------------------------

    async def call(self, session_id: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        context = self.sessions.get(session_id)
        if context is None:
            decision = Decision("deny", "unknown-session", "session was not started by the proxy")
        else:
            decision = check(self.policy, tool, args, context, self.agent)
        overhead_ms = round((time.perf_counter() - started) * 1000, 3)
        entry = self.ledger.append(session_id, tool, args, decision.decision, decision.rule, decision.reason)
        out: dict[str, Any] = {**decision.as_dict(), "seq": entry["seq"], "overhead_ms": overhead_ms}
        if decision.decision == "allow":
            await self._forward(tool, args, out)
        elif decision.decision == "approval":
            approval_id = f"ap-{entry['seq']}"
            self.pending[approval_id] = {"session_id": session_id, "tool": tool, "args": args}
            out["approval_id"] = approval_id
        self._publish({"type": "decision", "tool": tool, "entry": entry, "overhead_ms": overhead_ms,
                       **({"approval_id": out["approval_id"]} if "approval_id" in out else {})})
        return out

    async def _forward(self, tool: str, args: dict[str, Any], out: dict[str, Any]) -> None:
        try:
            out["result"] = await call_tool(self._servers, tool, args)
        except (WorldError, KeyError, ValueError) as exc:
            out["error"] = str(exc)

    async def approve(self, approval_id: str, approver: str) -> dict[str, Any]:
        pending = self.pending.pop(approval_id)  # KeyError: unknown or already decided
        entry = self.ledger.append(pending["session_id"], pending["tool"], pending["args"], "allow",
                                   f"human:{approver}", "approved by a human")
        out: dict[str, Any] = {"decision": "allow", "rule": entry["rule"], "reason": entry["reason"], "seq": entry["seq"]}
        await self._forward(pending["tool"], pending["args"], out)
        self._publish({"type": "decision", "tool": pending["tool"], "entry": entry, "overhead_ms": 0.0})
        return out

    async def reject(self, approval_id: str, approver: str) -> dict[str, Any]:
        pending = self.pending.pop(approval_id)
        entry = self.ledger.append(pending["session_id"], pending["tool"], pending["args"], "deny",
                                   f"human:{approver}", "rejected by a human")
        self._publish({"type": "decision", "tool": pending["tool"], "entry": entry, "overhead_ms": 0.0})
        return {"decision": "deny", "rule": entry["rule"], "reason": entry["reason"], "seq": entry["seq"]}

    # -- MCP surface for the agent --------------------------------------------------------------

    async def tool_specs(self) -> list[dict[str, Any]]:
        """Backend tools the policy does not deny (denied tools are not even advertised)."""
        if self._tool_specs is None:
            self._tool_specs = await list_tools(self._servers)
        tools = next((a["tools"] for a in self.policy.get("agents", []) if a["name"] == self.agent), {})
        return [t for t in self._tool_specs if tools.get(t["tool"], {}).get("mode", "deny") != "deny"]

    def mcp_server(self, session_id: str) -> Server:
        """An MCP server bound to one session; this is all the agent ever connects to."""

        async def on_list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
            return types.ListToolsResult(tools=[
                types.Tool(name=to_mcp_name(t["tool"]), description=t["description"], input_schema=t["input_schema"])
                for t in await self.tool_specs()
            ])

        async def on_call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
            out = await self.call(session_id, from_mcp_name(params.name), dict(params.arguments or {}))
            if out["decision"] == "allow" and "error" not in out:
                return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(out["result"]))])
            refusal = {k: out[k] for k in ("decision", "rule", "reason", "approval_id", "error") if k in out}
            return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(refusal))], is_error=True)

        return Server("agentchaincut-proxy", instructions="All tool calls are checked against a least-privilege policy.",
                      on_list_tools=on_list_tools, on_call_tool=on_call_tool)
