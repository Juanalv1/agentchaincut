"""Run the live agent N times per side and record transcripts for offline replay.

    python -m eval.live [--runs 3] [--out eval/results/live] [--policy artifacts/policy.yaml]

Needs ANTHROPIC_API_KEY (env or git-ignored .env). Writes one JSON per run plus summary.json;
the leak rate is reported with its n (measured), never extrapolated.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import yaml

from acc import llm as claude
from acc.pipeline import run_pipeline
from eval.live.agent import MODEL, SYSTEM_PROMPT, DirectBackend, ProxyBackend, poisoned_ticket, run_agent
from proxy.core import Proxy
from proxy.ledger import Ledger
from world.data import World

ROOT = Path(__file__).resolve().parents[2]


async def _one(side: str, policy: dict, seed: int, run: int) -> dict:
    world = World(seed=seed)
    customers = sorted(world.customers)
    ticket = poisoned_ticket(world, attacker_customer_id=customers[run % 50], victim_id=customers[-1 - run])
    if side == "unprotected":
        backend = DirectBackend(world)
    else:
        proxy = Proxy(world, world.service_key, policy, Ledger())
        backend = ProxyBackend(proxy, proxy.start_session(ticket["ticket_id"]))
    result = await run_agent(backend, ticket["ticket_id"])
    return {"side": side, "run": run, "ticket": ticket["body"], **result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.live")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", default=str(ROOT / "eval" / "results" / "live"))
    parser.add_argument("--policy", default=str(ROOT / "artifacts" / "policy.yaml"))
    parser.add_argument("--seed", type=int, default=26)
    args = parser.parse_args(argv)
    if not claude.available():
        print("eval.live: needs ANTHROPIC_API_KEY (env or .env) and `pip install -e '.[llm]'`", file=sys.stderr)
        return 2
    if not Path(args.policy).exists():
        run_pipeline(ROOT / "world", Path(args.policy).parent, seed=args.seed)
    policy = yaml.safe_load(Path(args.policy).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {"model": MODEL, "system_prompt": SYSTEM_PROMPT, "runs": args.runs, "label": "measured", "sides": {}}
    for side in ("unprotected", "protected"):
        leaks = 0
        for run in range(args.runs):
            record = asyncio.run(_one(side, policy, args.seed, run))
            (out / f"{side}-{run}.json").write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
            leaks += record["leaked"]
            print(f"{side} run {run}: leaked={record['leaked']} tools={[s['tool'] for s in record['steps']]}")
        summary["sides"][side] = {"n": args.runs, "leaked": leaks}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["sides"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
