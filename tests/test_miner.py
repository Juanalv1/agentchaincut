"""T05: relational invariant miner with filters, reject reasons and suggestion status."""

from __future__ import annotations

import copy

from acc import contracts
from acc.miner import approve, mine
from acc.traces import generate_sessions, split_customers
from world.data import World

EXPECTED_SUGGESTED = {
    ("billing.invoice_read", "invoice_id", "in", "customer.invoice_ids"),
    ("billing.refund", "invoice_id", "in", "customer.invoice_ids"),
    ("mail.send", "to", "eq", "ticket.customer.email"),
    ("tickets.add_note", "ticket_id", "eq", "ticket.id"),
    ("tickets.get", "ticket_id", "eq", "ticket.id"),
}


def _training() -> list[dict]:
    world = World()
    train, _ = split_customers(world)
    return generate_sessions(world, train, n_legit=240, n_abuse=80, seed=26)


def _key(inv: dict) -> tuple[str, str, str, str]:
    return inv["tool"], inv["arg"], inv["op"], inv["ctx_path"]


def test_mined_invariants_validate_against_the_schema() -> None:
    contracts.validate("invariants", mine(_training()))


def test_exactly_the_session_binding_rules_pass_the_filters() -> None:
    invariants = mine(_training())
    assert {_key(i) for i in invariants if i["status"] == "suggested"} == EXPECTED_SUGGESTED
    for inv in invariants:
        if inv["status"] == "suggested":
            assert inv["violations"] == 0 and inv["distinct"] >= 5


def test_each_reject_reason_is_reported_with_its_candidate() -> None:
    by_key = {_key(i): i for i in mine(_training())}
    assert by_key[("tickets.add_note", "author", "eq", "agent.id")]["reject_reason"] == "constant"
    assert by_key[("billing.refund", "currency", "eq", "customer.currency")]["reject_reason"] == "distinct<5"
    assert by_key[("mail.send", "to", "eq", "ticket.reporter_email")]["reject_reason"] == "untrusted_ctx"
    coincidental = by_key[("billing.invoice_read", "invoice_id", "eq", "customer.last_invoice_id")]
    assert coincidental["reject_reason"] == "coincidental" and coincidental["violations"] > 0
    assert all(i.get("note") for i in by_key.values())


def test_abuse_sessions_are_ignored() -> None:
    sessions = _training()
    legit_only = [s for s in sessions if s["label"] == "legit"]
    assert mine(sessions) == mine(legit_only)


def test_few_sessions_fail_the_distinct_filter() -> None:
    few = [s for s in _training() if s["label"] == "legit" and s["task_id"] == "acknowledge_ticket"][:3]
    by_key = {_key(i): i for i in mine(few)}
    assert by_key[("mail.send", "to", "eq", "ticket.customer.email")]["reject_reason"] == "distinct<5"


def test_ids_are_stable_and_unique() -> None:
    a, b = mine(_training()), mine(_training())
    assert [i["id"] for i in a] == [i["id"] for i in b]
    assert len({i["id"] for i in a}) == len(a)


def test_approve_promotes_suggestions_only() -> None:
    invariants = mine(_training())
    original = copy.deepcopy(invariants)
    approved = approve(invariants)
    assert invariants == original  # input untouched
    assert {_key(i) for i in approved if i["status"] == "accepted"} == EXPECTED_SUGGESTED
    assert not any(i["status"] == "suggested" for i in approved)
    first = next(i["id"] for i in invariants if i["status"] == "suggested")
    partial = approve(invariants, ids=[first])
    assert sum(i["status"] == "accepted" for i in partial) == 1
    contracts.validate("invariants", approved)
