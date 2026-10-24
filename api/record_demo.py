"""Record a demo run (one legit session, the poisoned-ticket attack, one approval) through the
real proxy and write it as JSON for the dashboard's offline replay mode.

    python -m api.record_demo web/public/demo/live.json
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def record(out: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        client = TestClient(create_app(artifacts_dir=Path(tmp) / "artifacts", world_dir=ROOT / "world"))
        session = client.post("/live/sessions", json={"customer_id": "C-010", "body": "Hi, please resend my last invoice."}).json()
        sid, ctx = session["session_id"], session["context"]
        client.post(f"/live/sessions/{sid}/calls", json={"tool": "tickets.get", "args": {"ticket_id": session["ticket_id"]}})
        client.post(f"/live/sessions/{sid}/calls", json={"tool": "billing.invoice_read",
                                                          "args": {"invoice_id": ctx["customer.invoice_ids"][-1]}})
        client.post(f"/live/sessions/{sid}/calls", json={"tool": "mail.send", "args": {
            "to": ctx["ticket.customer.email"], "subject": "Your invoice", "body": "Attached."}})
        refund = client.post(f"/live/sessions/{sid}/calls", json={"tool": "billing.refund", "args": {
            "invoice_id": ctx["customer.invoice_ids"][0], "amount": 10.0, "currency": ctx["customer.currency"]}}).json()
        client.post(f"/live/approvals/{refund['approval_id']}", json={"approver": "ops@store.test", "approve": True})
        attack = client.post("/live/attack").json()
        data = {"attack": attack, "ledger": client.get("/ledger").json(), "verify": client.get("/ledger/verify").json()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "web" / "public" / "demo" / "live.json")
    result = record(target)
    print(f"recorded {len(result['ledger'])} ledger entries to {target}")
