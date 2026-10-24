"""T06: shared policy engine (fail-closed) and the reachability proof ("before" path)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from acc import contracts
from acc.classify import classify, load_overrides
from acc.discover import discover
from acc.policy_engine import check, permissive_policy
from acc.reachability import find_path, prove, scripted_attack
from world.data import World
from world.servers import build_servers

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load((ROOT / "contracts" / "fixtures" / "policy.yaml").read_text())
CTX = {
    "ticket.id": "T-17",
    "ticket.customer.email": "ana@acme.test",
    "customer.invoice_ids": ["I-9", "I-12"],
}


def _catalog(world: World) -> list[dict]:
    tools = asyncio.run(discover(build_servers(world, world.service_key)))
    return classify(tools, overrides=load_overrides(ROOT / "world" / "overrides.json"))


def test_scoped_call_inside_the_session_is_allowed_with_its_rule() -> None:
    decision = check(POLICY, "mail.send", {"to": "ana@acme.test", "subject": "s", "body": "b"}, CTX)
    assert decision.decision == "allow" and decision.rule == "inv-3"
    assert decision.reason == "to == ticket.customer.email"


def test_scoped_call_outside_the_session_is_denied_with_reason() -> None:
    decision = check(POLICY, "mail.send", {"to": "eve@evil.test"}, CTX)
    assert (decision.decision, decision.rule) == ("deny", "inv-3")
    assert decision.reason == "to != ticket.customer.email"
    decision = check(POLICY, "billing.invoice_read", {"invoice_id": "I-99"}, CTX)
    assert decision.reason == "invoice_id not in customer.invoice_ids"


def test_modes_deny_and_approval() -> None:
    assert check(POLICY, "billing.invoice_list_all", {"status": "any"}, CTX).decision == "deny"
    approval = check(POLICY, "billing.refund", {"invoice_id": "I-9", "amount": 5}, CTX)
    assert approval.decision == "approval"


def test_engine_fails_closed() -> None:
    assert check(POLICY, "shell.exec", {}, CTX).decision == "deny"  # unknown tool
    assert check(POLICY, "mail.send", {}, CTX).decision == "deny"  # missing argument
    assert check(POLICY, "mail.send", {"to": "ana@acme.test"}, {}).decision == "deny"  # missing context
    assert check(None, "mail.send", {"to": "ana@acme.test"}, CTX).decision == "deny"  # no policy
    assert check(POLICY, "mail.send", {"to": "x"}, CTX, agent="other").decision == "deny"  # unknown agent
    broken = {"agents": [{"name": "support-agent", "tools": {"mail.send": {"mode": "scoped", "constraints": [{}]}}}]}
    assert check(broken, "mail.send", {"to": "x"}, CTX).decision == "deny"  # engine error


def test_approval_mode_still_enforces_constraints() -> None:
    policy = {"agents": [{"name": "support-agent", "tools": {"billing.refund": {
        "mode": "approval",
        "constraints": [{"arg": "invoice_id", "op": "in", "ctx": "customer.invoice_ids", "invariant": "inv-2"}],
    }}}]}
    assert check(policy, "billing.refund", {"invoice_id": "I-9", "amount": 1}, CTX).decision == "approval"
    assert check(policy, "billing.refund", {"invoice_id": "I-99", "amount": 1}, CTX).decision == "deny"


def test_permissive_policy_allows_every_catalog_tool() -> None:
    catalog = _catalog(World())
    policy = permissive_policy(catalog)
    contracts.validate("policy", policy)
    for tool in catalog:
        assert check(policy, tool["tool"], {}, {}).decision == "allow"


def test_find_path_goes_from_untrusted_to_sensitive_to_sink() -> None:
    path = find_path(_catalog(World()))
    assert path["path"] == ["tickets.get", "billing.invoice_read", "mail.send"]
    assert path["legs"] == ["U", "S", "X"]


def test_before_policy_the_scripted_attack_leaks_another_tenants_invoice() -> None:
    world = World()
    catalog = _catalog(world)
    attack = scripted_attack(world, victim_id="C-002", attacker_customer_id="C-001")
    proof = prove(world, catalog, attack, policy=None)
    contracts.validate("verify", {
        "reachability_before": proof["result"], "heldout": {"n": 0, "pass": 0},
        "abuse": {"n": 0, "blocked": 0}, "false_deny": {"n": 0, "count": 0},
        "residual": [], "labels": {},
    })
    assert proof["result"]["allowed"] is True
    assert world.outbox[-1]["to"] == "attacker@evil.test"
    assert attack["victim_invoice"] in world.outbox[-1]["body"]


def test_after_policy_the_same_calls_are_refused_and_nothing_leaks() -> None:
    world = World()
    catalog = _catalog(world)
    attack = scripted_attack(world, victim_id="C-002", attacker_customer_id="C-001")
    proof = prove(world, catalog, attack, policy=POLICY)
    assert proof["result"]["allowed"] is False
    assert [step["decision"] for step in proof["steps"]][1] == "deny"
    assert world.outbox == []

