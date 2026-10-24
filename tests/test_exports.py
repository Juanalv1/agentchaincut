"""T10: exports — Claude Code PreToolUse hook, Progent-style JSON, Assay-style YAML."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from acc.export.assay import export_assay
from acc.export.hook import export_hook
from acc.export.progent import export_progent

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load((ROOT / "contracts" / "fixtures" / "policy.yaml").read_text())
CTX = {"ticket.id": "T-17", "ticket.customer.email": "ana@acme.test", "customer.invoice_ids": ["I-9", "I-12"]}


def _run_hook(tmp_path: Path, tool_name: str, tool_input: dict, context: dict | None = CTX) -> dict | None:
    script = tmp_path / "acc_hook.py"
    script.write_text(export_hook(POLICY), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "ACC_SESSION_CONTEXT"}
    env["PYTHONPATH"] = str(ROOT)
    if context is not None:
        ctx_file = tmp_path / "ctx.json"
        ctx_file.write_text(json.dumps(context), encoding="utf-8")
        env["ACC_SESSION_CONTEXT"] = str(ctx_file)
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    done = subprocess.run([sys.executable, str(script)], input=json.dumps(payload), env=env,
                          capture_output=True, text=True, check=True)
    return json.loads(done.stdout) if done.stdout.strip() else None


def _decision(out: dict | None) -> str | None:
    return out["hookSpecificOutput"]["permissionDecision"] if out else None


def test_hook_allows_in_session_calls(tmp_path: Path) -> None:
    out = _run_hook(tmp_path, "mcp__mail__send", {"to": "ana@acme.test", "subject": "s", "body": "b"})
    assert _decision(out) == "allow"
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_hook_denies_exfiltration_with_reason(tmp_path: Path) -> None:
    out = _run_hook(tmp_path, "mcp__mail__send", {"to": "eve@evil.test", "subject": "s", "body": "b"})
    assert _decision(out) == "deny"
    assert "to != ticket.customer.email" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_hook_maps_proxy_names_and_asks_for_approval(tmp_path: Path) -> None:
    out = _run_hook(tmp_path, "mcp__acc__billing__refund", {"invoice_id": "I-9", "amount": 5})
    assert _decision(out) == "ask"


def test_hook_fails_closed_without_context_and_for_unknown_tools(tmp_path: Path) -> None:
    assert _decision(_run_hook(tmp_path, "mcp__mail__send", {"to": "ana@acme.test"}, context=None)) == "deny"
    assert _decision(_run_hook(tmp_path, "mcp__billing__export_everything", {})) == "deny"


def test_hook_leaves_non_policy_tools_alone(tmp_path: Path) -> None:
    assert _run_hook(tmp_path, "Read", {"file_path": "/tmp/x"}) is None
    assert _run_hook(tmp_path, "mcp__github__list_issues", {}) is None


def test_progent_export_instantiates_session_values() -> None:
    progent = export_progent(POLICY, CTX)
    [rule] = progent["mail.send"]
    assert rule["effect"] == 0
    assert rule["conditions"]["to"] == {"type": "string", "enum": ["ana@acme.test"]}
    assert progent["billing.invoice_read"][0]["conditions"]["invoice_id"]["enum"] == ["I-9", "I-12"]
    assert progent["billing.invoice_list_all"][0]["effect"] == 1
    assert progent["billing.refund"][0]["effect"] == 1  # no approval in Progent: fail closed
    json.dumps(progent)


def test_assay_export_is_default_deny_yaml() -> None:
    doc = yaml.safe_load(export_assay(POLICY))
    assert doc["default"] == "deny"
    tools = {t["name"]: t for t in doc["tools"]}
    assert tools["mail.send"]["when"] == [{"arg": "to", "equals_context": "ticket.customer.email"}]
    assert tools["billing.invoice_read"]["when"] == [{"arg": "invoice_id", "in_context": "customer.invoice_ids"}]
    assert tools["billing.refund"]["decision"] == "ask"
    assert "billing.invoice_list_all" not in tools
