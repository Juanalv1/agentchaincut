"""T11: cross-tenant benchmark, baselines and results table."""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _setup():
    world = World()
    catalog = classify(asyncio.run(discover(build_servers(world, world.service_key))),
                       overrides=load_overrides(ROOT / "world" / "overrides.json"))
    train, heldout = split_customers(world)
    sessions = generate_sessions(world, train, n_legit=240, n_abuse=0, seed=26)
    policy = optimize(catalog, approve(mine(sessions)), sessions)
    return world, catalog, sessions, policy, heldout_sessions(world, heldout, seed=1026)


def _row(baseline):
    world, catalog, sessions, policy, variants = _setup()
    return evaluate(baseline, variants)


def test_no_defense_leaks_everything_and_breaks_nothing() -> None:
    _, catalog, *_ = _setup()
    row = _row(NoDefense())
    assert row["attack_success"] == {"n": 300, "count": 300}
    assert row["utility"] == {"n": 200, "pass": 200}


def test_acc_policy_blocks_every_attack_without_false_denies() -> None:
    _, _, _, policy, _ = _setup()
    row = _row(AccPolicy(policy))
    assert row["attack_success"]["count"] == 0
    assert row["utility"]["pass"] == 200
    assert row["false_deny"]["count"] == 0
    assert row["label"] == "measured"


def test_taint_only_breaks_refunds_and_misses_cross_tenant_reads() -> None:
    _, catalog, *_ = _setup()
    row = _row(TaintOnly(catalog))
    assert row["false_deny"]["count"] > 0
    assert row["false_deny_by_task"]["refund_request"] > 0
    assert row["attack_success_by_family"]["foreign_object_id"] > 0
    assert row["attack_success_by_family"]["foreign_recipient"] == 0


def test_static_allowlist_misses_valid_but_foreign_recipients() -> None:
    world, catalog, sessions, *_ = _setup()
    row = _row(StaticAllowlist(world, catalog, sessions))
    assert row["attack_success_by_family"]["cross_tenant_recipient"] > 0
    assert row["attack_success_by_family"]["foreign_recipient"] == 0
    assert row["attack_success_by_family"]["bulk_exfil"] == 0


def test_llm_policy_baseline_uses_the_cache_and_reports_variance(tmp_path: Path) -> None:
    world, catalog, _, _, variants = _setup()
    calls: list[str] = []

    def complete(prompt: str) -> str:
        calls.append(prompt)
        return json.dumps({"tools": {"tickets.get": {}, "billing.invoice_read": {},
                                     "mail.send": {"to": ["attacker@evil.test"]}}})

    llm = LLMPolicy(catalog, tmp_path / "cache.json", complete=complete, runs=2)
    sample = [s for s in variants if s["label"] == "legit"][:2] + [s for s in variants if s["label"] == "abuse"][:2]
    row = evaluate(llm, sample)
    assert row["utility"]["n"] == 2 and row["attack_success"]["n"] == 2
    assert row["policy_variance"]["runs"] == 2
    first = len(calls)
    evaluate(LLMPolicy(catalog, tmp_path / "cache.json", complete=complete, runs=2), sample)
    assert len(calls) == first  # served from cache


def test_results_markdown_has_one_row_per_baseline_with_n() -> None:
    world, catalog, sessions, policy, variants = _setup()
    rows = [evaluate(b, variants) for b in (NoDefense(), TaintOnly(catalog),
                                             StaticAllowlist(world, catalog, sessions), AccPolicy(policy))]
    table = results_markdown(rows)
    for name in ("No defense", "Taint-only", "Static allowlist", "AgentChainCut"):
        assert name in table
    assert "n=300" in table and "n=200" in table


def test_stratified_sample_is_balanced_and_covers_every_kind() -> None:
    from eval.crosstenant.__main__ import stratified_sample

    *_, variants = _setup()
    sample = stratified_sample(variants, 24)
    assert sum(s["label"] == "legit" for s in sample) == 12
    assert len({s["task_id"] for s in sample if s["label"] == "legit"}) == 6
    from acc.traces import ABUSE_FAMILIES

    assert len({s["attack"] for s in sample if s["label"] == "abuse"}) == len(ABUSE_FAMILIES)


def test_llm_policy_matches_numbers_written_as_text(tmp_path: Path) -> None:
    *_, variants = _setup()
    _, catalog, *_ = _setup()
    refund = next(s for s in variants if s["label"] == "legit" and s["task_id"] == "refund_request")
    call = next(c for c in refund["calls"] if c["tool"] == "billing.refund")
    answer = {"tools": {c["tool"]: {} for c in refund["calls"]}}
    answer["tools"]["billing.refund"] = {"amount": [str(call["args"]["amount"])]}
    llm = LLMPolicy(catalog, tmp_path / "c.json", complete=lambda p: json.dumps(answer))
    index = refund["calls"].index(call)
    assert llm.decide(refund, index) == "allow"
