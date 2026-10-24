"""Progent-style JSON export.

Progent rules compare arguments with constants, so they cannot say "the customer of *this*
session". The export therefore instantiates the policy for one session context: `eq` becomes a
one-value enum, `in` the session's list. Progent has no approval mode, so approval tools are
exported as forbidden (fail-closed). Shape per tool: a list of
`{"priority", "effect" (0 allow, 1 forbid), "conditions" (JSON Schema per argument), "fallback"}`.
"""

from __future__ import annotations

from typing import Any

ALLOW, FORBID = 0, 1


def _schema(op: str, value: Any) -> dict[str, Any]:
    values = list(value) if op == "in" and isinstance(value, list) else [value]
    kind = "string" if all(isinstance(v, str) for v in values) else "number"
    return {"type": kind, "enum": values}


def export_progent(policy: dict[str, Any], context: dict[str, Any], agent: str = "support-agent") -> dict[str, Any]:
    tools = next(a["tools"] for a in policy["agents"] if a["name"] == agent)
    out: dict[str, Any] = {}
    for tool, rule in tools.items():
        if rule["mode"] in ("deny", "approval"):
            out[tool] = [{"priority": 1, "effect": FORBID, "conditions": {}, "fallback": FORBID}]
            continue
        conditions = {}
        for c in rule.get("constraints", []):
            if c["ctx"] not in context:
                conditions = None
                break
            conditions[c["arg"]] = _schema(c["op"], context[c["ctx"]])
        if conditions is None:  # missing session value: fail closed
            out[tool] = [{"priority": 1, "effect": FORBID, "conditions": {}, "fallback": FORBID}]
        else:
            out[tool] = [{"priority": 1, "effect": ALLOW, "conditions": conditions, "fallback": FORBID}]
    return out
