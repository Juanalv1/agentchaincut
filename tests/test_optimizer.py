"""T07: CP-SAT optimizer, unsat core -> conflict report, split-agent check."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

from acc import contracts
from acc.classify import classify, load_overrides
from acc.discover import discover
from acc.miner import approve, mine
from acc.optimizer import optimize
from acc.policy_engine import check
from acc.traces import generate_sessions, split_customers
from world.data import World
from world.servers import build_servers

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _inputs() -> tuple[list[dict], list[dict], list[dict]]:
    world = World()
    catalog = classify(asyncio.run(discover(build_servers(world, world.service_key))),
                       overrides=load_overrides(ROOT / "world" / "overrides.json"))
    train, _ = split_customers(world)
    sessions = generate_sessions(world, train, n_legit=240, n_abuse=0, seed=26)
    return catalog, sessions, approve(mine(sessions))


def _modes(policy: dict) -> dict[str, str]:
    return {tool: rule["mode"] for tool, rule in policy["agents"][0]["tools"].items()}


def test_policy_validates_and_breaks_no_task() -> None:
    catalog, sessions, invariants = _inputs()
    policy = optimize(catalog, invariants, sessions)
    contracts.validate("policy", policy)
    assert policy["solver"]["status"] == "OPTIMAL"
    assert policy["solver"]["method"] == "cp-sat"
    assert policy["solver"]["broken_tasks"] == []


def test_least_privilege_modes() -> None:
    catalog, sessions, invariants = _inputs()
    assert _modes(optimize(catalog, invariants, sessions)) == {
        "tickets.get": "scoped",
        "tickets.add_note": "scoped",
        "billing.invoice_read": "scoped",
        "billing.invoice_list": "scoped",
        "billing.invoice_list_all": "deny",
        "billing.refund": "approval",
        "mail.send": "scoped",
    }


def test_scoped_and_approval_tools_carry_their_invariants() -> None:
    catalog, sessions, invariants = _inputs()
    tools = optimize(catalog, invariants, sessions)["agents"][0]["tools"]
    accepted = {i["id"]: i for i in invariants if i["status"] == "accepted"}
    mail = tools["mail.send"]["constraints"]
    assert [(c["arg"], c["op"], c["ctx"]) for c in mail] == [("to", "eq", "ticket.customer.email")]
    assert all(c["invariant"] in accepted for t in tools.values() for c in t.get("constraints", []))
    assert [c["arg"] for c in tools["billing.refund"]["constraints"]] == ["invoice_id"]


def test_rule_of_two_conflict_is_reported_with_minimal_core_and_fixes() -> None:
    catalog, sessions, invariants = _inputs()
    policy = optimize(catalog, invariants, sessions)
    [conflict] = policy["conflicts"]
    assert conflict["task"] == "refund_request"
    assert conflict["legs"] == ["U", "S", "X"]
    assert conflict["core"] == ["billing.refund"]
    fixes = {f["type"]: f for f in conflict["fixes"]}
    assert fixes["approval_edge"]["tool"] == "billing.refund"
    assert fixes["split_agent"]["partition"] == [
        ["tickets.get", "tickets.add_note", "mail.send"],
        ["billing.invoice_read", "billing.invoice_list", "billing.refund"],
    ]
    assert conflict["resolved_by"] == "approval_edge"
    assert policy["legs_per_session"] == {"U": True, "S": True, "X": "bounded"}


def test_every_legit_training_call_is_still_permitted() -> None:
    catalog, sessions, invariants = _inputs()
    policy = optimize(catalog, invariants, sessions)
    for session in sessions:
        for call in session["calls"]:
            decision = check(policy, call["tool"], call["args"], session["context"])
            assert decision.decision in ("allow", "approval"), (session["task_id"], call, decision)


def test_exhaustive_fallback_matches_cp_sat() -> None:
    catalog, sessions, invariants = _inputs()
    cp = optimize(catalog, invariants, sessions)
    ex = optimize(catalog, invariants, sessions, method="exhaustive")
    assert ex["solver"]["method"] == "exhaustive"
    assert _modes(ex) == _modes(cp)
    assert ex["solver"]["objective"] == cp["solver"]["objective"]


def test_without_accepted_invariants_nothing_is_scoped() -> None:
    catalog, sessions, invariants = _inputs()
    suggested_only = mine(sessions)  # nothing approved by a human yet
    policy = optimize(catalog, suggested_only, sessions)
    assert "scoped" not in _modes(policy).values()
    assert policy["solver"]["broken_tasks"] == []
    assert _modes(policy)["mail.send"] == "approval"
