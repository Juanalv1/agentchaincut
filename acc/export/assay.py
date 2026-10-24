"""Assay / AgentPerms-style YAML export: default deny, one entry per permitted tool, with the
relational conditions kept as references to session context (not instantiated)."""

from __future__ import annotations

from typing import Any

import yaml

_DECISION = {"allow": "allow", "scoped": "allow", "approval": "ask"}


def export_assay(policy: dict[str, Any], agent: str = "support-agent") -> str:
    tools = next(a["tools"] for a in policy["agents"] if a["name"] == agent)
    entries = []
    for name, rule in tools.items():
        if rule["mode"] == "deny":
            continue
        entry: dict[str, Any] = {"name": name, "decision": _DECISION[rule["mode"]]}
        when = [
            {"arg": c["arg"], ("equals_context" if c["op"] == "eq" else "in_context"): c["ctx"]}
            for c in rule.get("constraints", [])
        ]
        if when:
            entry["when"] = when
        entries.append(entry)
    doc = {"version": 1, "kind": "agent-permissions", "agent": agent, "default": "deny", "tools": entries}
    return yaml.safe_dump(doc, sort_keys=False)
