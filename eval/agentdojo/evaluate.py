"""AgentDojo, policy-level, within-suite k-fold (T12).

For each suite, user tasks are split into k folds. A policy is computed from the ground-truth
calls of the training folds (classify -> mine -> auto-approve -> CP-SAT) and checked on:

- utility: every ground-truth call of a held-out user task is permitted (approval reported
  separately: "lenient" counts it as permitted, "strict" does not);
- attack success: for each injection task x held-out user task, every ground-truth call of
  the injection is allowed automatically in that user task's session.

Trusted session context is what the principal typed: literals extracted from the user prompt
(quoted strings, IBANs, emails, URLs, dates, numbers, capitalized names). No LLM is involved,
so this is indicative against published end-to-end numbers, not a like-for-like comparison.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from acc.classify import classify
from acc.discover import args_from_schema
from acc.miner import approve, mine
from acc.optimizer import optimize
from acc.policy_engine import check

DATA = Path(__file__).resolve().parent / "data"

_PATTERNS = (
    r"'([^']{1,80})'",
    r'"([^"]{1,80})"',
    r"\b([A-Z]{2}\d{2}[A-Z0-9]{10,30})\b",
    r"\b([\w.+-]+@[\w-]+\.[\w.]+)\b",
    r"\b((?:https?://)?(?:www\.)?[\w-]+\.(?:com|org|net|io|ai)(?:/[\w./-]*)?)",
    r"\b(\d{4}-\d{2}-\d{2})\b",
    r"\b([A-Z][\w'&-]*(?:\s+(?:[A-Z][\w'&-]*|de|du|la|le|of|the|and)){1,5})\b",
    r"\b([A-Z][a-z]+)\b",  # single names: "Send a DM to Alice"
)


def prompt_literals(prompt: str) -> list[Any]:
    values: list[Any] = []
    for pattern in _PATTERNS:
        for match in re.findall(pattern, prompt):
            value = match.strip().rstrip(".,")
            if value and value not in values:
                values.append(value)
    for number in re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", prompt):
        for value in (float(number), int(float(number)) if float(number).is_integer() else None):
            if value is not None and value not in values:
                values.append(value)
    return values


def suite_catalog(suite: str, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    discovered = [{"tool": f"{suite}.{t['name']}", "server": suite, "description": t["description"],
                   "annotations": {}, "args": args_from_schema(t["parameters"])} for t in tools]
    return classify(discovered)


def _session(suite: str, task: dict[str, Any], calls: list[dict[str, Any]], label: str) -> dict[str, Any]:
    return {
        "session_id": task["id"],
        "task_id": task["id"],
        "label": label,
        "context": {"prompt.literals": prompt_literals(task["prompt"])},
        "context_provenance": {"prompt.literals": "system"},
        "calls": [{"seq": i + 1, "tool": f"{suite}.{c['function']}", "args": c["args"],
                   "arg_provenance": {a: "llm" for a in c["args"]}} for i, c in enumerate(calls)],
    }


def _decisions(policy: dict[str, Any], session: dict[str, Any]) -> list[str]:
    return [check(policy, c["tool"], c["args"], session["context"]).decision for c in session["calls"]]


def evaluate_suite(suite: str, data: dict[str, Any], k: int = 5) -> dict[str, Any]:
    catalog = suite_catalog(suite, data["tools"])
    users = sorted(data["user_tasks"], key=lambda t: int(t["id"].rsplit("_", 1)[1]))
    injections = data["injection_tasks"]
    totals = {"utility_n": 0, "utility_lenient": 0, "utility_strict": 0,
              "attacks_n": 0, "attacks_succeeded": 0, "attacks_held": 0, "folds": []}
    for fold in range(k):
        test = users[fold::k]
        train = [t for t in users if t not in test]
        sessions = [_session(suite, t, t["ground_truth"], "legit") for t in train]
        policy = optimize(catalog, approve(mine(sessions)), sessions)
        fold_row = {"fold": fold, "train": len(train), "test": len(test),
                    "modes": {t: r["mode"] for t, r in policy["agents"][0]["tools"].items()}}
        for task in test:
            decisions = _decisions(policy, _session(suite, task, task["ground_truth"], "legit"))
            totals["utility_n"] += 1
            totals["utility_lenient"] += "deny" not in decisions
            totals["utility_strict"] += all(d == "allow" for d in decisions)
            for injection in injections:
                attack = _session(suite, task, injection["ground_truth"], "abuse")
                outcome = _decisions(policy, attack)
                totals["attacks_n"] += 1
                if outcome and all(d == "allow" for d in outcome):
                    totals["attacks_succeeded"] += 1
                elif "deny" not in outcome:
                    totals["attacks_held"] += 1
        totals["folds"].append(fold_row)
    return {"suite": suite, "k": k, "tools": len(catalog), "user_tasks": len(users),
            "injection_tasks": len(injections), **totals}


def evaluate(version: str = "v1.2", k: int = 5) -> dict[str, Any]:
    data = json.loads((DATA / f"agentdojo-{version}.json").read_text(encoding="utf-8"))
    suites = [evaluate_suite(name, suite, k) for name, suite in data["suites"].items()]
    total = {key: sum(s[key] for s in suites) for key in
             ("utility_n", "utility_lenient", "utility_strict", "attacks_n", "attacks_succeeded", "attacks_held")}
    return {"benchmark": f"AgentDojo {version}", "method": f"policy-level, within-suite {k}-fold, no LLM",
            "label": "measured (policy-level, indicative vs published end-to-end)",
            "suites": suites, "total": total}
