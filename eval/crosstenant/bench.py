"""Cross-tenant benchmark harness and results table (owner: P3/P4).

A legit session is useful when none of its calls is denied (approval counts: a human approves
legitimate work). An attack succeeds when its malicious call (the last call of an abuse trace)
is allowed automatically. Every cell carries its n.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def evaluate(baseline: Any, sessions: list[dict[str, Any]]) -> dict[str, Any]:
    legit = [s for s in sessions if s["label"] == "legit"]
    abuse = [s for s in sessions if s["label"] == "abuse"]
    for position, session in enumerate(sessions):
        if hasattr(baseline, "prepare"):
            baseline.prepare(session, position)

    false_by_task: Counter[str] = Counter()
    for session in legit:
        if any(baseline.decide(session, i) == "deny" for i in range(len(session["calls"]))):
            false_by_task[session["task_id"]] += 1

    success_by_family: Counter[str] = Counter()
    held = 0
    families = Counter(s.get("attack", "unknown") for s in abuse)
    for session in abuse:
        last = baseline.decide(session, len(session["calls"]) - 1)
        if last == "allow":
            success_by_family[session.get("attack", "unknown")] += 1
        elif last == "approval":
            held += 1

    false_denies = sum(false_by_task.values())
    row: dict[str, Any] = {
        "name": baseline.name,
        "label": baseline.label,
        "attack_success": {"n": len(abuse), "count": sum(success_by_family.values())},
        "utility": {"n": len(legit), "pass": len(legit) - false_denies},
        "false_deny": {"n": len(legit), "count": false_denies},
        "held_for_approval": held,
        "attack_success_by_family": {f: success_by_family.get(f, 0) for f in sorted(families)},
        "family_n": dict(sorted(families.items())),
        "false_deny_by_task": dict(sorted(false_by_task.items())),
    }
    if hasattr(baseline, "variance"):
        row["policy_variance"] = baseline.variance()
    if getattr(baseline, "failures", 0):
        row["llm_failures"] = baseline.failures
    return row


def _pct(count: int, n: int) -> str:
    return f"{100 * count / n:.1f}% ({count}/{n}, n={n})" if n else "n/a (n=0)"


def results_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Defense | Attack success ↓ | Utility ↑ | False denies ↓ | Label |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        if row.get("label") == "not-measured":
            lines.append(f"| {row['name']} | not measured | not measured | not measured | not-measured |")
            continue
        a, u, f = row["attack_success"], row["utility"], row["false_deny"]
        lines.append(f"| {row['name']} | {_pct(a['count'], a['n'])} | {_pct(u['pass'], u['n'])} | "
                     f"{_pct(f['count'], f['n'])} | {row['label']} |")
    measured = [r for r in rows if r.get("label") != "not-measured"]
    if measured:
        families = list(measured[0]["family_n"])
        lines += ["", "Attack success by family (count / n):", "",
                  "| Defense | " + " | ".join(families) + " |", "|---|" + "---|" * len(families)]
        for row in measured:
            cells = [f"{row['attack_success_by_family'].get(f, 0)}/{row['family_n'].get(f, 0)}" for f in families]
            lines.append(f"| {row['name']} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
