"""Policy engine shared by the proxy, the verifier, the exports and the benchmark (owner: P1/P4).

`check()` is fail-closed: no policy, unknown agent, unknown tool, missing argument, missing
context field or any internal error all deny. Approval mode still enforces its constraints
before asking a human.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

DEFAULT_AGENT = "support-agent"


@dataclass(frozen=True)
class Decision:
    decision: str  # allow | deny | approval
    rule: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rule_id(constraint: dict[str, Any]) -> str:
    return constraint.get("invariant") or f"{constraint['arg']}-{constraint['op']}-{constraint['ctx']}"


def _check_constraint(constraint: dict[str, Any], args: dict[str, Any], ctx: dict[str, Any]) -> Decision | None:
    """Return a deny Decision when the constraint fails, None when it holds."""
    arg, op, path = constraint["arg"], constraint["op"], constraint["ctx"]
    rule = _rule_id(constraint)
    if arg not in args:
        return Decision("deny", rule, f"missing argument {arg}")
    if path not in ctx:
        return Decision("deny", rule, f"missing session context {path}")
    value, expected = args[arg], ctx[path]
    if op == "eq":
        if value != expected:
            return Decision("deny", rule, f"{arg} != {path}")
    elif op == "in":
        if not isinstance(expected, list) or value not in expected:
            return Decision("deny", rule, f"{arg} not in {path}")
    else:
        return Decision("deny", rule, f"unknown operator {op!r}")
    return None


def _describe(constraints: list[dict[str, Any]]) -> str:
    return " and ".join(f"{c['arg']} {'==' if c['op'] == 'eq' else 'in'} {c['ctx']}" for c in constraints)


def check(
    policy: dict[str, Any] | None,
    tool: str,
    args: dict[str, Any],
    ctx: dict[str, Any],
    agent: str = DEFAULT_AGENT,
) -> Decision:
    try:
        if not policy:
            return Decision("deny", None, "no policy loaded")
        agents = {a["name"]: a for a in policy.get("agents", [])}
        if agent not in agents:
            return Decision("deny", None, f"unknown agent {agent}")
        rule = agents[agent]["tools"].get(tool)
        if rule is None:
            return Decision("deny", "default-deny", f"{tool} is not in the policy")
        mode = rule["mode"]
        if mode == "deny":
            return Decision("deny", "mode:deny", f"{tool} is denied by policy")
        constraints = rule.get("constraints") or []
        for constraint in constraints:
            failed = _check_constraint(constraint, args or {}, ctx or {})
            if failed is not None:
                return failed
        if mode == "allow":
            return Decision("allow", "mode:allow", f"{tool} is allowed")
        if mode == "scoped":
            if not constraints:
                return Decision("deny", None, "scoped tool without constraints")
            return Decision("allow", ",".join(_rule_id(c) for c in constraints), _describe(constraints))
        if mode == "approval":
            suffix = f" ({_describe(constraints)})" if constraints else ""
            return Decision("approval", "mode:approval", f"{tool} requires human approval{suffix}")
        return Decision("deny", None, f"unknown mode {mode!r}")
    except Exception as exc:  # fail closed on anything unexpected
        return Decision("deny", "engine-error", f"policy engine error: {type(exc).__name__}")


def permissive_policy(catalog: list[dict[str, Any]], agent: str = DEFAULT_AGENT) -> dict[str, Any]:
    """The "before" state: every catalog tool allowed (what a broad backend credential grants)."""
    return {
        "agents": [{"name": agent, "tools": {t["tool"]: {"mode": "allow"} for t in catalog}}],
        "legs_per_session": {"U": True, "S": True, "X": True},
        "solver": {"status": "UNKNOWN", "objective": 0, "broken_tasks": []},
        "conflicts": [],
    }
