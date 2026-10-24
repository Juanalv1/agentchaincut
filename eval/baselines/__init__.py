"""Baselines for the cross-tenant benchmark (owner: P3/P4).

Every baseline answers `decide(session, index) -> "allow" | "deny" | "approval"` for the call at
`index` of a trace session, so all of them are scored by the same deterministic harness.
"""

from __future__ import annotations

from typing import Any

from acc.policy_engine import check
from world.data import World


class NoDefense:
    name, label = "No defense", "measured"

    def decide(self, session: dict[str, Any], index: int) -> str:
        return "allow"


class AccPolicy:
    name, label = "AgentChainCut", "measured"

    def __init__(self, policy: dict[str, Any]) -> None:
        self.policy = policy

    def decide(self, session: dict[str, Any], index: int) -> str:
        call = session["calls"][index]
        return check(self.policy, call["tool"], call["args"], session["context"]).decision


class TaintOnly:
    """Ikarus / CaMeL-style taint: an external-effect call may not take any argument derived
    from untrusted input (output of a U tool, user-typed or non-system context). Generous
    variant: text the agent writes itself ("llm") is not treated as tainted."""

    name, label = "Taint-only (Ikarus-like)", "measured"

    def __init__(self, catalog: list[dict[str, Any]]) -> None:
        self.legs = {t["tool"]: t["legs"] for t in catalog}

    def _tainted(self, provenance: str, session: dict[str, Any]) -> bool:
        if provenance == "user":
            return True
        if provenance.startswith("tool_output:"):
            tool = provenance.split(":", 1)[1].split("#", 1)[0]
            return self.legs.get(tool, {}).get("U", True)
        if provenance.startswith("context:"):
            return session["context_provenance"].get(provenance.split(":", 1)[1]) != "system"
        return False

    def decide(self, session: dict[str, Any], index: int) -> str:
        call = session["calls"][index]
        if not self.legs.get(call["tool"], {}).get("X", True):
            return "allow"
        tainted = any(self._tainted(p, session) for p in call["arg_provenance"].values())
        return "deny" if tainted else "allow"


class StaticAllowlist:
    """Progent-manual-style rules an admin would write: only the tools seen in legit work,
    recipients inside the customer directory, refunds under the largest legit amount. Static
    rules compare with constants, so they cannot express "this session's customer"."""

    name, label = "Static allowlist (Progent-manual-like)", "measured"

    def __init__(self, world: World, catalog: list[dict[str, Any]], training: list[dict[str, Any]]) -> None:
        legit_calls = [c for s in training if s["label"] == "legit" for c in s["calls"]]
        self.tools = {c["tool"] for c in legit_calls}
        self.recipients = {c.email for c in world.customers.values()}
        refunds = [c["args"]["amount"] for c in legit_calls if c["tool"] == "billing.refund"]
        self.max_refund = max(refunds) if refunds else 0.0

    def decide(self, session: dict[str, Any], index: int) -> str:
        call = session["calls"][index]
        tool, args = call["tool"], call["args"]
        if tool not in self.tools:
            return "deny"
        if tool == "mail.send" and args.get("to") not in self.recipients:
            return "deny"
        if tool == "billing.refund" and float(args.get("amount", 0)) > self.max_refund:
            return "deny"
        return "allow"
