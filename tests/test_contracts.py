"""Contract tests: every fixture validates, broken copies fail, ledger chain holds."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from acc import contracts
from acc.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "contracts" / "fixtures"

SCHEMA_NAMES = ["catalog", "trace", "invariants", "policy", "verify", "ledger_entry"]

FIXTURE_SCHEMA = {
    "catalog.json": "catalog",
    "traces.jsonl": "trace",
    "invariants.json": "invariants",
    "policy.yaml": "policy",
    "verify.json": "verify",
    "ledger.jsonl": "ledger_entry",
}


def load_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_jsonl(name: str) -> list[dict]:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_yaml(name: str):
    return yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))


# --- schemas ---------------------------------------------------------------


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_is_valid_draft_2020_12(name: str) -> None:
    schema = contracts.load_schema(name)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    jsonschema.Draft202012Validator.check_schema(schema)


def test_unknown_schema_name_raises() -> None:
    with pytest.raises(KeyError):
        contracts.load_schema("nope")


# --- fixtures validate -----------------------------------------------------


@pytest.mark.parametrize("fixture,schema", sorted(FIXTURE_SCHEMA.items()))
def test_fixture_validates_with_inferred_schema(fixture: str, schema: str) -> None:
    count = contracts.validate_file(FIXTURES / fixture)
    assert count >= 1


@pytest.mark.parametrize("fixture,schema", sorted(FIXTURE_SCHEMA.items()))
def test_fixture_validates_with_explicit_schema(fixture: str, schema: str) -> None:
    contracts.validate_file(FIXTURES / fixture, schema=schema)


def test_traces_have_legit_and_abuse_sessions() -> None:
    labels = [t["label"] for t in load_jsonl("traces.jsonl")]
    assert labels.count("legit") >= 3
    assert labels.count("abuse") >= 2


def test_fixtures_are_mutually_consistent() -> None:
    tools = {entry["tool"] for entry in load_json("catalog.json")}
    for trace in load_jsonl("traces.jsonl"):
        for call in trace["calls"]:
            assert call["tool"] in tools
    for inv in load_json("invariants.json"):
        assert inv["tool"] in tools
    policy = load_yaml("policy.yaml")
    for agent in policy["agents"]:
        assert set(agent["tools"]) <= tools
    for conflict in policy["conflicts"]:
        assert set(conflict["core"]) <= tools
    for entry in load_jsonl("ledger.jsonl"):
        assert entry["tool"] in tools


# --- broken copies fail ----------------------------------------------------


def _assert_invalid(schema: str, obj) -> None:
    with pytest.raises(jsonschema.ValidationError):
        contracts.validate(schema, obj)


def test_policy_with_invalid_mode_fails() -> None:
    policy = load_yaml("policy.yaml")
    policy["agents"][0]["tools"]["mail.send"]["mode"] = "maybe"
    _assert_invalid("policy", policy)


def test_policy_scoped_without_constraints_fails() -> None:
    policy = load_yaml("policy.yaml")
    policy["agents"][0]["tools"]["mail.send"] = {"mode": "scoped"}
    _assert_invalid("policy", policy)


def test_policy_constraint_with_invalid_op_fails() -> None:
    policy = load_yaml("policy.yaml")
    policy["agents"][0]["tools"]["mail.send"]["constraints"][0]["op"] = "neq"
    _assert_invalid("policy", policy)


def test_catalog_entry_missing_legs_fails() -> None:
    catalog = load_json("catalog.json")
    del catalog[0]["legs"]
    _assert_invalid("catalog", catalog)


def test_catalog_entry_with_unknown_source_fails() -> None:
    catalog = load_json("catalog.json")
    catalog[0]["source"] = "guess"
    _assert_invalid("catalog", catalog)


def test_trace_with_invalid_label_fails() -> None:
    trace = load_jsonl("traces.jsonl")[0]
    trace["label"] = "benign"
    _assert_invalid("trace", trace)


def test_trace_call_missing_arg_provenance_fails() -> None:
    trace = load_jsonl("traces.jsonl")[0]
    del trace["calls"][0]["arg_provenance"]
    _assert_invalid("trace", trace)


def test_trace_with_malformed_provenance_fails() -> None:
    trace = load_jsonl("traces.jsonl")[0]
    key = next(iter(trace["context_provenance"]))
    trace["context_provenance"][key] = "somewhere"
    _assert_invalid("trace", trace)


def test_rejected_invariant_without_reason_fails() -> None:
    invariants = load_json("invariants.json")
    rejected = next(i for i in invariants if i["status"] == "rejected")
    del rejected["reject_reason"]
    _assert_invalid("invariants", invariants)


def test_accepted_invariant_with_reject_reason_fails() -> None:
    invariants = load_json("invariants.json")
    accepted = next(i for i in invariants if i["status"] == "accepted")
    accepted["reject_reason"] = "constant"
    _assert_invalid("invariants", invariants)


def test_verify_with_invalid_claim_label_fails() -> None:
    verify = load_json("verify.json")
    verify["labels"]["heldout"] = "probably"
    _assert_invalid("verify", verify)


def test_ledger_entry_with_invalid_decision_fails() -> None:
    entry = load_jsonl("ledger.jsonl")[0]
    entry["decision"] = "maybe"
    _assert_invalid("ledger_entry", entry)


def test_validate_file_reports_broken_jsonl_line(tmp_path: Path) -> None:
    traces = load_jsonl("traces.jsonl")
    traces[1]["label"] = "benign"
    broken = tmp_path / "traces.jsonl"
    broken.write_text("\n".join(json.dumps(t) for t in traces) + "\n", encoding="utf-8")
    with pytest.raises(jsonschema.ValidationError) as excinfo:
        contracts.validate_file(broken)
    assert "line 2" in str(excinfo.value)


def test_validate_file_rejects_unknown_file_name(tmp_path: Path) -> None:
    unknown = tmp_path / "mystery.json"
    unknown.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        contracts.validate_file(unknown)


# --- ledger hash chain -----------------------------------------------------


def test_canonical_json_is_sorted_and_compact() -> None:
    assert contracts.canonical_json({"b": 1, "a": [1, "x"]}) == '{"a":[1,"x"],"b":1}'


def test_ledger_hash_matches_spec() -> None:
    import hashlib

    entry = {"seq": 1, "tool": "tickets.get", "hash": "ignored"}
    prev = contracts.GENESIS_HASH
    expected = hashlib.sha256(
        (prev + '{"seq":1,"tool":"tickets.get"}').encode("utf-8")
    ).hexdigest()
    assert contracts.ledger_hash(prev, entry) == expected


def test_ledger_fixture_chain_verifies() -> None:
    entries = load_jsonl("ledger.jsonl")
    assert len(entries) == 3
    assert entries[0]["prev"] == "0" * 64
    assert contracts.verify_ledger(entries) is None


def test_tampered_ledger_entry_breaks_chain() -> None:
    entries = load_jsonl("ledger.jsonl")
    tampered = copy.deepcopy(entries)
    tampered[1]["decision"] = "allow"
    assert contracts.verify_ledger(tampered) == 1


def test_dropped_ledger_entry_breaks_chain() -> None:
    entries = load_jsonl("ledger.jsonl")
    assert contracts.verify_ledger([entries[0], entries[2]]) == 1


# --- skeleton --------------------------------------------------------------


@pytest.mark.parametrize(
    "module",
    [
        "acc.export",
        "world",
        "proxy",
        "eval",
        "eval.crosstenant",
        "eval.agentdojo",
        "eval.baselines",
        "api",
    ],
)
def test_skeleton_packages_import(module: str) -> None:
    assert importlib.import_module(module).__doc__


def test_cli_run_is_not_implemented_yet(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["run", "world/"]) != 0
    assert "not implemented" in capsys.readouterr().err
