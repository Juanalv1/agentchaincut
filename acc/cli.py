"""`acc` command-line entry point (owner: P4)."""

from __future__ import annotations

import argparse
import json
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acc", description="AgentChainCut pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run discover -> optimize -> verify -> export on a world")
    run.add_argument("world_dir", help="directory holding the MCP world (e.g. world/)")
    run.add_argument("--out", default="artifacts", help="output directory (default: artifacts/)")
    run.add_argument("--seed", type=int, default=26)
    run.add_argument("--method", choices=["cp-sat", "exhaustive"], default="cp-sat")
    run.add_argument("--no-auto-approve", action="store_true",
                     help="leave mined invariants as suggestions (nothing gets scoped)")
    run.add_argument("--llm", action="store_true", help="use the cached LLM for tools no rule can classify")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        from pathlib import Path

        from acc.pipeline import run_pipeline

        if not Path(args.world_dir).is_dir():
            print(f"acc run: world directory not found: {args.world_dir}", file=sys.stderr)
            return 2
        summary = run_pipeline(args.world_dir, args.out, seed=args.seed, method=args.method,
                               auto_approve=not args.no_auto_approve, use_llm=args.llm)
        print(json.dumps(summary, indent=2))
        print(f"artifacts written to {args.out}/", file=sys.stderr)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
