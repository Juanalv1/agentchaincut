"""T04: tool discovery + Rule-of-Two leg classifier."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from acc import contracts
from acc.classify import LLMClassifier, classify, load_overrides
from acc.discover import arg_role, discover
from world.data import World
from world.servers import build_servers

ROOT = Path(__file__).resolve().parents[1]


def _catalog(overrides=None, llm=None) -> list[dict]:
    world = World()
    tools = asyncio.run(discover(build_servers(world, world.service_key)))
    return classify(tools, overrides=overrides, llm=llm)


def test_arg_roles_follow_argument_names() -> None:
    assert arg_role("invoice_id") == "object_id"
    assert arg_role("to") == "destination"
    assert arg_role("amount") == "amount"
    assert arg_role("body") == "content"
    assert arg_role("status") == "filter"
    assert arg_role("currency") == "other"


def test_discovered_catalog_validates_and_lists_every_tool() -> None:
    catalog = _catalog()
    contracts.validate("catalog", catalog)
    assert [t["tool"] for t in catalog] == [
        "tickets.get", "tickets.add_note", "billing.invoice_read",
        "billing.invoice_list_all", "billing.refund", "mail.send",
    ]


def test_legs_from_mcp_hints_and_heuristics() -> None:
    legs = {t["tool"]: t["legs"] for t in _catalog()}
    assert legs["tickets.get"] == {"U": True, "S": False, "X": False}
    assert legs["billing.invoice_read"] == {"U": False, "S": True, "X": False}
    assert legs["billing.invoice_list_all"] == {"U": False, "S": True, "X": False}
    assert legs["billing.refund"] == {"U": False, "S": False, "X": True}
    assert legs["mail.send"] == {"U": False, "S": False, "X": True}
    assert legs["tickets.add_note"] == {"U": False, "S": False, "X": True}


def test_manual_overrides_win() -> None:
    overrides = load_overrides(ROOT / "world" / "overrides.json")
    catalog = {t["tool"]: t for t in _catalog(overrides=overrides)}
    assert catalog["mail.send"]["source"] == "manual"
    assert catalog["tickets.get"]["source"] == "mcp_hint"


def test_tool_without_hints_or_known_verb_defaults_to_sink() -> None:
    tool = {"tool": "crm.frobnicate", "server": "crm", "description": "", "annotations": {},
            "args": [{"name": "x", "type": "string", "role": "other"}]}
    [entry] = classify([tool])
    assert entry["legs"] == {"U": False, "S": False, "X": True}
    assert "fail-closed" in entry["rationale"]


def test_verb_heuristic_without_hints() -> None:
    tool = {"tool": "crm.customer_list", "server": "crm", "description": "List customers.",
            "annotations": {}, "args": []}
    [entry] = classify([tool])
    assert entry["source"] == "heuristic"
    assert entry["legs"] == {"U": False, "S": True, "X": False}


def test_llm_is_consulted_only_for_unresolved_tools_and_cached(tmp_path: Path) -> None:
    calls: list[str] = []

    def complete(prompt: str) -> str:
        calls.append(prompt)
        return json.dumps({"U": True, "S": False, "X": False, "rationale": "reads web pages"})

    llm = LLMClassifier(tmp_path / "cache.json", complete=complete)
    tool = {"tool": "web.frobnicate", "server": "web", "description": "", "annotations": {}, "args": []}
    [entry] = classify([tool], llm=llm)
    assert entry["source"] == "llm" and entry["legs"]["U"] is True
    classify([tool], llm=LLMClassifier(tmp_path / "cache.json", complete=complete))
    assert len(calls) == 1  # second run served from the on-disk cache


def test_llm_garbage_falls_back_to_sink(tmp_path: Path) -> None:
    llm = LLMClassifier(tmp_path / "cache.json", complete=lambda prompt: "not json")
    tool = {"tool": "web.frobnicate", "server": "web", "description": "", "annotations": {}, "args": []}
    [entry] = classify([tool], llm=llm)
    assert entry["legs"]["X"] is True and entry["source"] == "heuristic"
