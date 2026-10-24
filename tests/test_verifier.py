"""T08: held-out variants, verifier and residual-risk search."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

from acc import contracts
from acc.classify import classify, load_overrides
from acc.discover import discover
from acc.miner import approve, mine
from acc.optimizer import optimize
from acc.policy_engine import permissive_policy
from acc.traces import ABUSE_FAMILIES, generate_sessions, split_customers
from acc.variants import heldout_sessions
from acc.verifier import residual_risk, verify
from world.data import World
from world.servers import build_servers

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _setup() -> tuple[World, list[dict], dict, list[dict]]:
    world = World()
    catalog = classify(asyncio.run(discover(build_servers(world, world.service_key))),
                       overrides=load_overrides(ROOT / "world" / "overrides.json"))
    train, heldout = split_customers(world)
    sessions = generate_sessions(world, train, n_legit=240, n_abuse=0, seed=26)
    policy = optimize(catalog, approve(mine(sessions)), sessions)
    return world, catalog, policy, heldout_sessions(world, heldout, seed=1026)


def test_heldout_variants_use_only_unseen_customers() -> None:
    world, _, _, variants = _setup()
    _, heldout = split_customers(world)
    assert sum(s["label"] == "legit" for s in variants) == 200
    assert sum(s["label"] == "abuse" for s in variants) == 300
    assert {s["context"]["customer.id"] for s in variants} <= set(heldout)


def test_policy_passes_heldout_and_blocks_every_abuse_family() -> None:
    _, catalog, policy, variants = _setup()
    report, details = verify(policy, catalog, variants)
    contracts.validate("verify", report)
    assert report["heldout"] == {"n": 200, "pass": 200}
    assert report["false_deny"] == {"n": 200, "count": 0}
    assert report["abuse"] == {"n": 300, "blocked": 300}
    assert set(details["abuse_by_family"]) == set(ABUSE_FAMILIES)
    for family, counts in details["abuse_by_family"].items():
        assert counts["blocked"] == counts["n"], family
    excess = details["abuse_by_family"]["excess_refund"]
    assert excess["held_for_approval"] == excess["n"]  # own invoice, inflated amount: a human decides
    assert report["labels"]["heldout"] == "measured"
    assert report["labels"]["live"] == "not-measured"



def test_permissive_policy_blocks_nothing() -> None:
    _, catalog, _, variants = _setup()
    report, _ = verify(permissive_policy(catalog), catalog, variants)
    assert report["abuse"]["blocked"] == 0
    assert report["heldout"]["pass"] == 200


def test_residual_risk_lists_unbound_sink_arguments_as_lower_bound() -> None:
    _, catalog, policy, _ = _setup()
    residual = {(r["sink"], r["arg"]): r for r in residual_risk(policy, catalog)}
    assert residual[("mail.send", "body")]["status"] == "unconstrained"
    assert residual[("tickets.add_note", "body")]["status"] == "unconstrained"
    assert residual[("billing.refund", "amount")]["status"] == "approval"
    assert ("mail.send", "to") not in residual
    assert all(r["claim"] == "lower-bound" for r in residual.values())


def test_reachability_is_included_when_given() -> None:
    _, catalog, policy, variants = _setup()
    before = {"path": ["tickets.get", "billing.invoice_read", "mail.send"], "legs": ["U", "S", "X"], "allowed": True}
    after = dict(before, allowed=False)
    report, _ = verify(policy, catalog, variants, reachability_before=before, reachability_after=after)
    assert report["reachability_after"]["allowed"] is False
