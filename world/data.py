"""In-memory backend for the demo support-agent world: customers, invoices, tickets and mail.

Everything is generated from a fixed seed so traces, verification and benchmarks are
reproducible. The MCP servers in `world.servers` are thin wrappers over this backend.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from typing import Any

AGENT_ID = "support-agent"
CURRENCIES = ("USD", "EUR", "VES")
INVOICE_STATUSES = ("paid", "open", "overdue")

_FIRST = (
    "ana", "luis", "maria", "pedro", "sofia", "diego", "valeria", "carlos", "lucia", "jose",
    "camila", "miguel", "isabel", "andres", "elena", "rafael", "paula", "jorge", "daniela", "tomas",
)
_LAST = (
    "garcia", "rodriguez", "perez", "gonzalez", "lopez", "martinez", "sanchez", "romero", "diaz",
    "torres", "ramirez", "flores", "rivas", "mendoza", "castillo", "silva", "rojas", "medina",
)
_COMPANIES = (
    "acme", "globex", "initech", "umbrella", "hooli", "stark", "wayne", "tyrell", "cyberdyne",
    "soylent", "wonka", "vandelay", "dunder", "pied", "aperture", "oscorp",
)


class WorldError(Exception):
    """A backend request failed (unknown id, invalid amount...)."""


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    email: str
    company: str
    currency: str


@dataclass
class Invoice:
    id: str
    customer_id: str
    amount: float
    currency: str
    status: str
    refunded: float = 0.0


@dataclass
class Ticket:
    id: str
    customer_id: str
    subject: str
    body: str
    reporter_email: str
    partner_id: str
    notes: list[dict[str, str]] = field(default_factory=list)


class World:
    """Seeded backend. `service_key` is the credential only the proxy (and servers) hold."""

    def __init__(self, seed: int = 26, n_customers: int = 200) -> None:
        self.seed = seed
        self._rng = random.Random(seed)
        self.service_key = f"sk-world-{seed:04d}-{self._rng.getrandbits(64):016x}"
        self.customers: dict[str, Customer] = {}
        self.invoices: dict[str, Invoice] = {}
        self.tickets: dict[str, Ticket] = {}
        self.outbox: list[dict[str, str]] = []
        self._invoice_seq = 0
        self._ticket_seq = 0
        self._generate(n_customers)

    # -- generation -------------------------------------------------------------------------

    def _generate(self, n_customers: int) -> None:
        rng = self._rng
        used: set[str] = set()
        for index in range(1, n_customers + 1):
            first, last, company = rng.choice(_FIRST), rng.choice(_LAST), rng.choice(_COMPANIES)
            email = f"{first}.{last}@{company}.test"
            suffix = 2
            while email in used:
                email = f"{first}.{last}{suffix}@{company}.test"
                suffix += 1
            used.add(email)
            customer = Customer(
                id=f"C-{index:03d}",
                name=f"{first.title()} {last.title()}",
                email=email,
                company=company,
                currency=rng.choice(CURRENCIES),
            )
            self.customers[customer.id] = customer
            for _ in range(rng.randint(1, 6)):
                self._new_invoice(customer)

    def _new_invoice(self, customer: Customer) -> Invoice:
        self._invoice_seq += 1
        invoice = Invoice(
            id=f"I-{self._invoice_seq:04d}",
            customer_id=customer.id,
            amount=round(self._rng.uniform(15, 900), 2),
            currency=customer.currency,
            status=self._rng.choice(INVOICE_STATUSES),
        )
        self.invoices[invoice.id] = invoice
        return invoice

    # -- backend queries --------------------------------------------------------------------

    def invoice_ids_of(self, customer_id: str) -> list[str]:
        return [i.id for i in self.invoices.values() if i.customer_id == customer_id]

    def open_ticket(
        self, customer_id: str, subject: str, body: str, reporter_email: str | None = None
    ) -> Ticket:
        customer = self._customer(customer_id)
        self._ticket_seq += 1
        ticket = Ticket(
            id=f"T-{self._ticket_seq:04d}",
            customer_id=customer.id,
            subject=subject,
            body=body,
            reporter_email=reporter_email or customer.email,
            partner_id=f"P-{self._rng.randint(1, 999):03d}",
        )
        self.tickets[ticket.id] = ticket
        return ticket

    def trusted_context(self, ticket_id: str) -> tuple[dict[str, Any], dict[str, str]]:
        """Session context the proxy fetches from the backend (never from agent text).

        Returns (context, provenance). Only `ticket.reporter_email` is user-typed.
        """
        ticket = self._ticket(ticket_id)
        customer = self.customers[ticket.customer_id]
        invoice_ids = self.invoice_ids_of(customer.id)
        context: dict[str, Any] = {
            "ticket.id": ticket.id,
            "ticket.customer.email": customer.email,
            "ticket.partner_id": ticket.partner_id,
            "ticket.reporter_email": ticket.reporter_email,
            "customer.id": customer.id,
            "customer.invoice_ids": invoice_ids,
            "customer.last_invoice_id": invoice_ids[-1],
            "customer.currency": customer.currency,
            "agent.id": AGENT_ID,
        }
        provenance = {path: "system" for path in context}
        provenance["ticket.reporter_email"] = "user"
        return context, provenance

    # -- backend operations (exposed as MCP tools) -----------------------------------------

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        ticket = self._ticket(ticket_id)
        return {
            "id": ticket.id,
            "customer_id": ticket.customer_id,
            "subject": ticket.subject,
            "body": ticket.body,
            "reporter_email": ticket.reporter_email,
            "notes": list(ticket.notes),
        }

    def add_note(self, ticket_id: str, body: str, author: str) -> dict[str, Any]:
        ticket = self._ticket(ticket_id)
        ticket.notes.append({"author": author, "body": body})
        return {"ticket_id": ticket.id, "notes": len(ticket.notes)}

    def invoice_read(self, invoice_id: str) -> dict[str, Any]:
        return asdict(self._invoice(invoice_id))

    def invoice_list(self, customer_id: str) -> list[dict[str, Any]]:
        customer = self._customer(customer_id)
        return [asdict(i) for i in self.invoices.values() if i.customer_id == customer.id]

    def invoice_list_all(self, status: str) -> list[dict[str, Any]]:
        if status not in INVOICE_STATUSES and status != "any":
            raise WorldError(f"unknown invoice status {status!r}")
        return [asdict(i) for i in self.invoices.values() if status in ("any", i.status)]

    def refund(self, invoice_id: str, amount: float, currency: str) -> dict[str, Any]:
        invoice = self._invoice(invoice_id)
        if currency != invoice.currency:
            raise WorldError(f"currency {currency} does not match invoice currency {invoice.currency}")
        if amount <= 0 or invoice.refunded + amount > invoice.amount:
            raise WorldError(f"refund {amount} exceeds refundable amount on {invoice_id}")
        invoice.refunded = round(invoice.refunded + amount, 2)
        return {"invoice_id": invoice.id, "refunded": invoice.refunded, "currency": currency}

    def send_mail(self, to: str, subject: str, body: str) -> dict[str, Any]:
        message = {"to": to, "subject": subject, "body": body}
        self.outbox.append(message)
        return {"queued": True, "id": f"M-{len(self.outbox):05d}"}

    def execute(self, tool: str, args: dict[str, Any]) -> Any:
        """Run one backend operation by qualified tool name (same surface as the MCP servers)."""
        handlers = {
            "tickets.get": lambda a: self.get_ticket(a["ticket_id"]),
            "tickets.add_note": lambda a: self.add_note(a["ticket_id"], a["body"], a.get("author", AGENT_ID)),
            "billing.invoice_read": lambda a: self.invoice_read(a["invoice_id"]),
            "billing.invoice_list": lambda a: {"invoices": self.invoice_list(a["customer_id"])},
            "billing.invoice_list_all": lambda a: {"invoices": self.invoice_list_all(a.get("status", "any"))},
            "billing.refund": lambda a: self.refund(a["invoice_id"], a["amount"], a["currency"]),
            "mail.send": lambda a: self.send_mail(a["to"], a["subject"], a["body"]),
        }
        if tool not in handlers:
            raise WorldError(f"unknown tool {tool!r}")
        try:
            return handlers[tool](args)
        except KeyError as exc:
            raise WorldError(f"missing argument {exc.args[0]!r} for {tool}") from None

    # -- helpers ----------------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "customers": [asdict(c) for c in self.customers.values()],
            "invoices": [asdict(i) for i in self.invoices.values()],
            "tickets": [asdict(t) for t in self.tickets.values()],
            "outbox": list(self.outbox),
        }

    def _customer(self, customer_id: str) -> Customer:
        try:
            return self.customers[customer_id]
        except KeyError:
            raise WorldError(f"unknown customer {customer_id!r}") from None

    def _ticket(self, ticket_id: str) -> Ticket:
        try:
            return self.tickets[ticket_id]
        except KeyError:
            raise WorldError(f"unknown ticket {ticket_id!r}") from None

    def _invoice(self, invoice_id: str) -> Invoice:
        try:
            return self.invoices[invoice_id]
        except KeyError:
            raise WorldError(f"unknown invoice {invoice_id!r}") from None
