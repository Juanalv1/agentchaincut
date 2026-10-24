"""Serve the proxy over MCP stdio for one ticket session.

    python -m proxy --policy artifacts/policy.yaml --ticket T-0001 [--ledger artifacts/ledger.jsonl]

The backend world and its service credential live in this process; the connecting agent only
sees the proxy's tools.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml
from mcp.server.stdio import stdio_server

from proxy.core import Proxy
from proxy.ledger import Ledger
from world.data import World


async def _serve(args: argparse.Namespace) -> None:
    world = World(seed=args.seed)
    policy = yaml.safe_load(Path(args.policy).read_text(encoding="utf-8"))
    proxy = Proxy(world, world.service_key, policy, Ledger(args.ledger))
    ticket_id = args.ticket or world.open_ticket("C-001", "Invoice copy", "Please resend my last invoice.").id
    server = proxy.mcp_server(proxy.start_session(ticket_id))
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m proxy", description="AgentChainCut MCP proxy (stdio)")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--ticket", help="ticket id to bind the session to (default: open a demo ticket)")
    parser.add_argument("--ledger", default=None, help="append decisions to this JSONL file")
    parser.add_argument("--seed", type=int, default=26)
    asyncio.run(_serve(parser.parse_args(argv)))


if __name__ == "__main__":
    main()
