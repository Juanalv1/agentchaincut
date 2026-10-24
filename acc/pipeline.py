"""End-to-end offline pipeline: discover -> classify -> traces -> mine -> optimize -> verify -> export.

Every stage writes one artifact that validates against its schema in `contracts/`. Mined
suggestions are auto-approved by default for the demo, and the run summary says so.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import yaml

from acc import contracts
from acc.classify import LLMClassifier, classify, load_overrides
from acc.discover import discover
from acc.export.assay import export_assay
from acc.export.hook import export_hook
from acc.export.progent import export_progent
from acc.miner import approve, mine
from acc.optimizer import optimize
from acc.reachability import find_path, prove, scripted_attack
from acc.traces import generate_sessions, split_customers
from acc.variants import heldout_sessions
from acc.verifier import verify
from world.data import World
from world.servers import build_servers

TRAIN_LEGIT, TRAIN_ABUSE = 240, 80


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def run_pipeline(
    world_dir: str | Path,
    out_dir: str | Path,
    *,
    seed: int = 26,
    method: str = "cp-sat",
    auto_approve: bool = True,
    use_llm: bool = False,
) -> dict[str, Any]:
    world_dir, out = Path(world_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "export").mkdir(exist_ok=True)
    timings: dict[str, float] = {}

    def timed(name: str, fn, *args, **kwargs):
        started = time.perf_counter()
        result = fn(*args, **kwargs)
        timings[name] = round(time.perf_counter() - started, 3)
        return result

    world = World(seed=seed)
    tools = timed("discover", lambda: asyncio.run(discover(build_servers(world, world.service_key))))
    llm = LLMClassifier(out / ".cache" / "classify.json") if use_llm else None
    catalog = timed("classify", classify, tools, overrides=load_overrides(world_dir / "overrides.json"), llm=llm)
    _write_json(out / "catalog.json", catalog)

    train, heldout = split_customers(world, seed=seed)
    sessions = timed("traces", generate_sessions, world, train, n_legit=TRAIN_LEGIT, n_abuse=TRAIN_ABUSE, seed=seed)
    _write_jsonl(out / "traces.jsonl", sessions)

    mined = timed("mine", mine, sessions)
    invariants = approve(mined) if auto_approve else mined
    _write_json(out / "invariants.json", invariants)

    policy = timed("optimize", optimize, catalog, invariants, sessions, method=method)
    (out / "policy.yaml").write_text(
        "# Least-privilege policy computed by `acc run` (AgentChainCut). Unlisted tools are denied.\n"
        + yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    # Reachability: execute the same scripted attack on two identical fresh worlds.
    proofs = {}
    for label, active_policy in (("before", None), ("after", policy)):
        replay = World(seed=seed)
        attack = scripted_attack(replay, victim_id=heldout[0], attacker_customer_id=heldout[1])
        proofs[label] = prove(replay, catalog, attack, active_policy)
    _write_json(out / "reachability.json", {**proofs, "graph_path": find_path(catalog)})

    variants = timed("variants", heldout_sessions, world, heldout, seed=seed + 1000)
    report, details = timed("verify", verify, policy, catalog, variants,
                            reachability_before=proofs["before"]["result"],
                            reachability_after=proofs["after"]["result"])
    _write_json(out / "verify.json", report)
    _write_json(out / "verify_details.json", details)
    _write_jsonl(out / "heldout.jsonl", variants)

    example = next(s for s in variants if s["label"] == "legit")
    (out / "export" / "acc_hook.py").write_text(export_hook(policy), encoding="utf-8")
    _write_json(out / "export" / "progent.json", {
        "session_id": example["session_id"],
        "note": "Progent rules compare with constants, so this policy is instantiated for one session.",
        "policy": export_progent(policy, example["context"]),
    })
    (out / "export" / "assay.yaml").write_text(export_assay(policy), encoding="utf-8")
    _write_json(out / "export" / "session_context.example.json", example["context"])

    for name in ("catalog.json", "traces.jsonl", "invariants.json", "policy.yaml", "verify.json"):
        contracts.validate_file(out / name)

    summary = {
        "seed": seed,
        "method": method,
        "approval": "auto-approved suggestions (demo mode)" if auto_approve else "suggestions awaiting human approval",
        "counts": {
            "tools": len(catalog),
            "training_sessions": len(sessions),
            "invariants_accepted": sum(i["status"] == "accepted" for i in invariants),
            "invariants_suggested": sum(i["status"] == "suggested" for i in invariants),
            "invariants_rejected": sum(i["status"] == "rejected" for i in invariants),
        },
        "solver": policy["solver"],
        "conflicts": len(policy["conflicts"]),
        "reachability": {k: v["result"]["allowed"] for k, v in proofs.items()},
        "verify": {k: report[k] for k in ("heldout", "abuse", "false_deny")},
        "labels": report["labels"],
        "timings_s": timings,
    }
    _write_json(out / "run.json", summary)
    return summary

