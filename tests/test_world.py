"""T02: mock business world (tickets, billing, mail) and its MCP servers."""

from __future__ import annotations

import asyncio
import json

import pytest

from world.data import World, WorldError
from world.servers import TOOL_NAMES, build_servers, call_tool, list_tools


def test_world_is_deterministic_for_a_seed() -> None:
    a, b = World(seed=7), World(seed=7)
    assert [c.email for c in a.customers.values()] == [c.email for c in b.customers.values()]
    assert list(a.invoices) == list(b.invoices)
    assert World(seed=8).customers["C-001"].email != a.customers["C-001"].email or list(
        World(seed=8).invoices
    ) != list(a.invoices)


def test_world_has_200_customers_with_unique_emails_and_owned_invoices() -> None:
    world = World()
    assert len(world.customers) == 200
    assert len({c.email for c in world.customers.values()}) == 200
    for invoice in world.invoices.values():
        assert invoice.customer_id in world.customers
    for customer in world.customers.values():
        assert world.invoice_ids_of(customer.id), customer.id


def test_trusted_context_comes_from_backend_records() -> None:
    world = World()
    ticket = world.open_ticket("C-005", "Invoice copy", "Please resend my invoice.")
    ctx, prov = world.trusted_context(ticket.id)
    customer = world.customers["C-005"]
    assert ctx["ticket.id"] == ticket.id
    assert ctx["ticket.customer.email"] == customer.email
    assert ctx["customer.id"] == "C-005"
    assert ctx["customer.invoice_ids"] == world.invoice_ids_of("C-005")
    assert ctx["agent.id"] == "support-agent"
    assert prov["ticket.customer.email"] == "system"
    # The reporter address is typed by the customer, so it is not trusted.
    assert prov["ticket.reporter_email"] == "user"
    assert set(ctx) == set(prov)


def test_unknown_ids_raise_world_error() -> None:
    world = World()
    with pytest.raises(WorldError):
        world.get_ticket("T-404")
    with pytest.raises(WorldError):
        world.invoice_read("I-404")
    with pytest.raises(WorldError):
        world.trusted_context("T-404")


def test_refund_cannot_exceed_invoice_amount() -> None:
    world = World()
    invoice = next(iter(world.invoices.values()))
    with pytest.raises(WorldError):
        world.refund(invoice.id, invoice.amount + 1, invoice.currency)
    result = world.refund(invoice.id, 1.0, invoice.currency)
    assert result["refunded"] == 1.0


def test_send_mail_lands_in_outbox() -> None:
    world = World()
    world.send_mail("ana@acme.test", "Hi", "Body")
    assert world.outbox[-1] == {"to": "ana@acme.test", "subject": "Hi", "body": "Body"}


def test_servers_require_the_service_credential() -> None:
    world = World()
    with pytest.raises(PermissionError):
        build_servers(world, "wrong-key")


def test_servers_expose_the_catalog_tools_with_mcp_hints() -> None:
    world = World()
    servers = build_servers(world, world.service_key)
    tools = asyncio.run(list_tools(servers))
    names = [t["tool"] for t in tools]
    assert names == list(TOOL_NAMES)
    by_name = {t["tool"]: t for t in tools}
    assert by_name["tickets.get"]["annotations"]["readOnlyHint"] is True
    assert by_name["billing.refund"]["annotations"]["destructiveHint"] is True
    assert by_name["mail.send"]["input_schema"]["required"] == ["to", "subject", "body"]


def test_call_tool_round_trips_through_mcp() -> None:
    world = World()
    servers = build_servers(world, world.service_key)
    invoice_id = world.invoice_ids_of("C-001")[0]
    result = asyncio.run(call_tool(servers, "billing.invoice_read", {"invoice_id": invoice_id}))
    assert result["id"] == invoice_id
    assert result["customer_id"] == "C-001"
    asyncio.run(call_tool(servers, "mail.send", {"to": "x@y.test", "subject": "s", "body": "b"}))
    assert world.outbox[-1]["to"] == "x@y.test"


def test_call_tool_surfaces_world_errors() -> None:
    world = World()
    servers = build_servers(world, world.service_key)
    with pytest.raises(WorldError):
        asyncio.run(call_tool(servers, "billing.invoice_read", {"invoice_id": "I-404"}))


def test_world_snapshot_is_json_serializable() -> None:
    assert json.dumps(World().snapshot())


def test_execute_dispatches_by_qualified_tool_name() -> None:
    world = World()
    invoice_id = world.invoice_ids_of("C-003")[0]
    assert world.execute("billing.invoice_read", {"invoice_id": invoice_id})["customer_id"] == "C-003"


def test_execute_rejects_unknown_tools_and_missing_arguments() -> None:
    world = World()
    with pytest.raises(WorldError):
        world.execute("shell.exec", {})
    with pytest.raises(WorldError):
        world.execute("mail.send", {"to": "a@b.test"})
