"""`acc run world/` end to end: every artifact is written and validates."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from acc import contracts
from acc.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]


def test_acc_run_produces_catalog_policy_and_verify(tmp_path: Path, capsys) -> None:
    out = tmp_path / "artifacts"
    assert cli_main(["run", str(ROOT / "world"), "--out", str(out)]) == 0
    summary = json.loads(capsys.readouterr().out)
    for name in ("catalog.json", "traces.jsonl", "invariants.json", "policy.yaml", "verify.json"):
        assert contracts.validate_file(out / name) >= 1
    for name in ("acc_hook.py", "progent.json", "assay.yaml", "session_context.example.json"):
        assert (out / "export" / name).exists()
    assert summary["solver"]["status"] == "OPTIMAL" and summary["solver"]["broken_tasks"] == []
    assert summary["reachability"] == {"before": True, "after": False}
    assert summary["verify"]["heldout"]["pass"] == summary["verify"]["heldout"]["n"]
    assert summary["verify"]["abuse"]["blocked"] == summary["verify"]["abuse"]["n"]
    assert summary["approval"].startswith("auto-approved")
    policy = yaml.safe_load((out / "policy.yaml").read_text())
    assert policy["agents"][0]["tools"]["mail.send"]["mode"] == "scoped"


def test_acc_run_without_approval_scopes_nothing(tmp_path: Path, capsys) -> None:
    out = tmp_path / "artifacts"
    assert cli_main(["run", str(ROOT / "world"), "--out", str(out), "--no-auto-approve"]) == 0
    policy = yaml.safe_load((out / "policy.yaml").read_text())
    assert "scoped" not in {r["mode"] for r in policy["agents"][0]["tools"].values()}
