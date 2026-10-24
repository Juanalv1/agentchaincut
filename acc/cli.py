"""`acc` command-line entry point (owner: P4). Stub until the pipeline lands."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acc", description="AgentChainCut pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run discover -> optimize -> verify on a world")
    run.add_argument("world_dir", help="directory holding the MCP world (e.g. world/)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        print(f"acc run {args.world_dir}: not implemented", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
