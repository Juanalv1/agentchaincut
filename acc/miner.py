"""Relational invariant miner, Daikon-style over a restricted grammar (owner: P3).

Candidates: for every (tool, arg) seen in legit calls and every context field,
`arg == ctx.field` (scalar field) or `arg in ctx.field` (list field). A candidate passes only
with 0 violations, >= `min_distinct` distinct values, no constant value and a context field
whose provenance is `system` in every session. Passing candidates are `suggested` until a
human approves them (`approve`); everything else is kept as `rejected` with its reason.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Iterable

MIN_DISTINCT = 5
MIN_HOLD = 0.5  # candidates holding in fewer calls are noise and are not reported


def _hashable(value: Any) -> Any:
    return tuple(value) if isinstance(value, list) else value


def _holds(op: str, value: Any, ctx_value: Any) -> bool:
    if op == "in":
        return isinstance(ctx_value, list) and value in ctx_value
    return value == ctx_value


def mine(
    sessions: Iterable[dict[str, Any]],
    *,
    min_distinct: int = MIN_DISTINCT,
    min_hold: float = MIN_HOLD,
) -> list[dict[str, Any]]:
    """Mine invariants from the legit sessions in `sessions` (abuse sessions are ignored)."""
    legit = [s for s in sessions if s.get("label") == "legit"]

    ctx_kind: dict[str, str] = {}
    untrusted_paths: set[str] = set()
    for session in legit:
        for path, value in session["context"].items():
            ctx_kind.setdefault(path, "in" if isinstance(value, list) else "eq")
            if session["context_provenance"].get(path) != "system":
                untrusted_paths.add(path)

    # (tool, arg) -> list of (arg value, session context)
    observations: dict[tuple[str, str], list[tuple[Any, dict[str, Any]]]] = defaultdict(list)
    for session in legit:
        for call in session["calls"]:
            for arg, value in call["args"].items():
                if isinstance(value, (dict, list)):
                    continue  # the grammar only binds scalar arguments
                observations[(call["tool"], arg)].append((value, session["context"]))

    candidates: list[dict[str, Any]] = []
    for (tool, arg), obs in observations.items():
        distinct = len({_hashable(v) for v, _ in obs})
        for path, op in ctx_kind.items():
            held = sum(path in ctx and _holds(op, value, ctx[path]) for value, ctx in obs)
            if held == 0 or held / len(obs) < min_hold:
                continue
            violations = len(obs) - held
            candidate: dict[str, Any] = {
                "tool": tool, "arg": arg, "op": op, "ctx_path": path,
                "support": len(obs), "distinct": distinct, "violations": violations,
            }
            relation = f"{arg} {'==' if op == 'eq' else 'in'} {path}"
            if violations:
                candidate.update(status="rejected", reject_reason="coincidental",
                                 note=f"{relation} broke in {violations} of {len(obs)} legit calls.")
            elif distinct == 1:
                candidate.update(status="rejected", reject_reason="constant",
                                 note="Same value in every session; binds nothing session-specific.")
            elif path in untrusted_paths:
                candidate.update(status="rejected", reject_reason="untrusted_ctx",
                                 note=f"{path} is not fetched from the backend (provenance is not 'system').")
            elif distinct < min_distinct:
                candidate.update(status="rejected", reject_reason="distinct<5",
                                 note=f"Only {distinct} distinct values observed; too few to rule out coincidence.")
            else:
                candidate.update(status="suggested",
                                 note=f"{relation} held in all {len(obs)} legit calls; awaiting human approval.")
            candidates.append(candidate)

    rank = {"suggested": 0, "rejected": 1}
    candidates.sort(key=lambda c: (rank[c["status"]], c["tool"], c["arg"], c["ctx_path"]))
    ordered = []
    for index, candidate in enumerate(candidates, start=1):
        ordered.append({"id": f"inv-{index}", **candidate})
    return ordered


def approve(invariants: list[dict[str, Any]], ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Return a copy where the given suggestions (all of them when `ids` is None) are accepted."""
    wanted = None if ids is None else set(ids)
    out = copy.deepcopy(invariants)
    for inv in out:
        if inv["status"] == "suggested" and (wanted is None or inv["id"] in wanted):
            inv["status"] = "accepted"
            inv["note"] = inv["note"].replace("awaiting human approval", "approved")
    return out
