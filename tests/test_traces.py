"""T03: trace generator (6 legit task types, abuse families, fixed seed, provenance)."""

from __future__ import annotations

from acc import contracts
from acc.traces import ABUSE_FAMILIES, LEGIT_TASKS, generate_sessions, split_customers
from world.data import World


def _sessions(seed: int = 1, n_legit: int = 60, n_abuse: int = 40) -> list[dict]:
    world = World()
    train, _ = split_customers(world, seed=seed)
    return generate_sessions(world, train, n_legit=n_legit, n_abuse=n_abuse, seed=seed)


def test_generation_is_deterministic_for_a_seed() -> None:
    assert _sessions(seed=3) == _sessions(seed=3)
    assert _sessions(seed=3) != _sessions(seed=4)


def test_every_session_validates_against_the_trace_schema() -> None:
    for session in _sessions():
        contracts.validate("trace", session)


def test_all_legit_tasks_and_abuse_families_are_generated() -> None:
    sessions = _sessions()
    assert len(LEGIT_TASKS) == 6
    assert {s["task_id"] for s in sessions if s["label"] == "legit"} == set(LEGIT_TASKS)
    assert {s["attack"] for s in sessions if s["label"] == "abuse"} == set(ABUSE_FAMILIES)
    assert sum(s["label"] == "legit" for s in sessions) == 60
    assert sum(s["label"] == "abuse" for s in sessions) == 40


def test_legit_calls_stay_inside_the_session_tenant() -> None:
    for session in _sessions():
        if session["label"] != "legit":
            continue
        ctx = session["context"]
        for call in session["calls"]:
            args = call["args"]
            if call["tool"] == "mail.send":
                assert args["to"] == ctx["ticket.customer.email"]
            if call["tool"] in ("billing.invoice_read", "billing.refund"):
                assert args["invoice_id"] in ctx["customer.invoice_ids"]
            if call["tool"] == "billing.invoice_list":
                assert args["customer_id"] == ctx["customer.id"]
            if call["tool"] in ("tickets.get", "tickets.add_note"):
                assert args["ticket_id"] == ctx["ticket.id"]


def test_abuse_sessions_end_with_the_malicious_call() -> None:
    for session in _sessions():
        if session["label"] != "abuse":
            continue
        ctx = session["context"]
        last = session["calls"][-1]
        attack, args = session["attack"], last["args"]
        if attack in ("foreign_recipient", "cross_tenant_recipient", "injected_context"):
            assert last["tool"] == "mail.send" and args["to"] != ctx["ticket.customer.email"]
        elif attack in ("foreign_object_id", "foreign_refund"):
            assert args["invoice_id"] not in ctx["customer.invoice_ids"]
        elif attack == "cross_ticket":
            assert last["tool"] == "tickets.add_note" and args["ticket_id"] != ctx["ticket.id"]
        elif attack == "foreign_list":
            assert last["tool"] == "billing.invoice_list" and args["customer_id"] != ctx["customer.id"]
        elif attack == "bulk_exfil":
            assert last["tool"] == "billing.invoice_list_all"
        elif attack == "excess_refund":
            assert last["tool"] == "billing.refund" and args["invoice_id"] in ctx["customer.invoice_ids"]


def test_injected_values_carry_untrusted_provenance() -> None:
    for session in _sessions():
        if session["label"] == "abuse" and session["attack"] != "bulk_exfil":
            provenance = session["calls"][-1]["arg_provenance"]
            assert not any(v == "system" for v in provenance.values())


def test_legit_traces_have_enough_distinct_entities_for_mining() -> None:
    sessions = [s for s in _sessions() if s["label"] == "legit"]
    assert len({s["context"]["ticket.customer.email"] for s in sessions}) >= 20


def test_customer_split_is_disjoint_and_complete() -> None:
    world = World()
    train, heldout = split_customers(world, seed=1)
    assert not set(train) & set(heldout)
    assert set(train) | set(heldout) == set(world.customers)
    assert len(train) == 120
