"""Run the cross-tenant benchmark and write eval/results/crosstenant.{json,md}.

    python -m eval.crosstenant [--out eval/results] [--llm-sample 24] [--llm-runs 3]

Deterministic baselines run on every held-out session. The LLM-written-policy baseline costs
API calls, so it runs on a stratified sample (and is compared with the others on that same
sample); its answers are cached in eval/results/llm_policy_cache.json so reruns are free.
Without an API key that row is reported as not-measured.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from acc import llm as claude
from acc.classify import classify, load_overrides
from acc.discover import discover
from acc.miner import approve, mine
from acc.optimizer import optimize
from acc.traces import generate_sessions, split_customers
from acc.variants import heldout_sessions
from eval.baselines import AccPolicy, NoDefense, StaticAllowlist, TaintOnly
from eval.baselines.llm_policy import LLMPolicy
from eval.crosstenant.bench import evaluate, results_markdown
from world.data import World
from world.servers import build_servers

ROOT = Path(__file__).resolve().parents[2]


def stratified_sample(sessions: list[dict], size: int) -> list[dict]:
    """Half legit, half abuse; round-robin over task types and abuse families inside each half."""
    def round_robin(pool: list[dict], key: str, count: int) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for s in pool:
            groups.setdefault(s.get(key) or "", []).append(s)
        picked, depth = [], 0
        while len(picked) < count and any(len(g) > depth for g in groups.values()):
            for name in sorted(groups):
                if depth < len(groups[name]) and len(picked) < count:
                    picked.append(groups[name][depth])
            depth += 1
        return picked

    legit = [s for s in sessions if s["label"] == "legit"]
    abuse = [s for s in sessions if s["label"] == "abuse"]
    return round_robin(legit, "task_id", size // 2) + round_robin(abuse, "attack", size - size // 2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.crosstenant")
    parser.add_argument("--out", default=str(ROOT / "eval" / "results"))
    parser.add_argument("--seed", type=int, default=26)
    parser.add_argument("--llm-sample", type=int, default=24)
    parser.add_argument("--llm-runs", type=int, default=3)
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    world = World(seed=args.seed)
    catalog = classify(asyncio.run(discover(build_servers(world, world.service_key))),
                       overrides=load_overrides(ROOT / "world" / "overrides.json"))
    train, heldout = split_customers(world, seed=args.seed)
    training = generate_sessions(world, train, n_legit=240, n_abuse=80, seed=args.seed)
    policy = optimize(catalog, approve(mine(training)), training)
    variants = heldout_sessions(world, heldout, seed=args.seed + 1000)

    baselines = [NoDefense(), TaintOnly(catalog), StaticAllowlist(world, catalog, training), AccPolicy(policy)]
    full_rows = [evaluate(b, variants) for b in baselines]

    sample = stratified_sample(variants, args.llm_sample)
    cache = out / "llm_policy_cache.json"
    llm_row: dict
    if args.no_llm or not (claude.available() or cache.exists()):
        llm_row = {"name": LLMPolicy.name, "label": "not-measured",
                   "reason": "no ANTHROPIC_API_KEY and no cached answers"}
    else:
        llm_row = evaluate(LLMPolicy(catalog, cache, runs=args.llm_runs), sample)
    sample_rows = [evaluate(b, sample) for b in baselines] + [llm_row]

    results = {"heldout_full": full_rows, "llm_sample": sample_rows,
               "notes": {"attack_success": "malicious call (last of an abuse trace) allowed automatically",
                         "utility": "legit session with no denied call (approval counts as pass)",
                         "world": "synthetic, modeled on Zendesk/Stripe/Gmail-like APIs"}}
    (out / "crosstenant.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    md = ["# Cross-tenant benchmark", "",
          f"Held-out sessions from {len(heldout)} customers never seen in training (seed {args.seed}).", "",
          results_markdown(full_rows), "",
          f"## Stratified sample with the LLM-written-policy baseline (n={len(sample)})", "",
          results_markdown(sample_rows)]
    variance = llm_row.get("policy_variance")
    if variance:
        md += ["", f"LLM policy variance: {variance['sessions_with_differing_policies']} of "
                   f"{variance['sessions']} sessions got different policies across {variance['runs']} runs "
                   f"(mean distinct policies {variance['distinct_policies_mean']})."]
    (out / "crosstenant.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
