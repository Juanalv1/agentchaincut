"""T12: AgentDojo policy-level, within-suite k-fold evaluation (from the exported data)."""

from __future__ import annotations

import json

from eval.agentdojo.evaluate import DATA, evaluate_suite, prompt_literals


def test_prompt_literals_extracts_principal_values() -> None:
    lits = prompt_literals("Send 12.00 to GB29NWBK60161331926819 and email 'bill.txt' to bob@x.com, then tell Alice.")
    assert "GB29NWBK60161331926819" in lits and "bill.txt" in lits and "bob@x.com" in lits
    assert 12.0 in lits and "Alice" in lits


def test_exported_data_has_the_four_v1_2_suites() -> None:
    data = json.loads((DATA / "agentdojo-v1.2.json").read_text(encoding="utf-8"))
    assert set(data["suites"]) == {"workspace", "travel", "banking", "slack"}
    assert sum(len(s["user_tasks"]) for s in data["suites"].values()) == 97


def test_suite_evaluation_counts_are_consistent() -> None:
    data = json.loads((DATA / "agentdojo-v1.2.json").read_text(encoding="utf-8"))
    row = evaluate_suite("banking", data["suites"]["banking"], k=4)
    assert row["utility_n"] == 16
    assert row["attacks_n"] == 16 * 9
    assert row["attacks_succeeded"] + row["attacks_held"] <= row["attacks_n"]
    assert row["utility_strict"] <= row["utility_lenient"] <= row["utility_n"]
    assert len(row["folds"]) == 4
