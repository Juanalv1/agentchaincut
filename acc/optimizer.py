"""Rule-of-Two least-privilege optimizer on OR-Tools CP-SAT (owner: P4).

Per tool, pick one mode in {allow, scoped, approval, deny}:

- `scoped` needs at least one accepted invariant; its constraints are those invariants.
  `approval` keeps the same constraints and adds a human in the loop.
- A task is preserved when none of its tools is denied and every traced call satisfies the
  constraints of its scoped tools (approval counts as preserved: a human approves it).
- Legs per task session: U and S are present whenever a tool with that leg is used (scoping a
  read to the session's tenant does not make the data less sensitive). X is neutralized by
  approval, or by `scoped` when every attacker-steerable argument (object id, destination,
  amount) is bound by an invariant. Preserved tasks must hold at most two active legs.
- Objective (least privilege): 100 per broken task + mode cost (deny 0, scoped 1, allow 2,
  approval 3), so unused tools are denied and needed ones get the narrowest working mode.

When no policy keeps every task without new human approvals, assumption literals plus
`SufficientAssumptionsForInfeasibility` (shrunk to a minimal core by deletion) give the
conflict report, with two fixes: approval on the core tools or splitting the agent.
`method="exhaustive"` is the labeled fallback search for small catalogs.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from acc.policy_engine import _check_constraint

MODES = ("allow", "scoped", "approval", "deny")
MODE_COST = {"deny": 0, "scoped": 1, "allow": 2, "approval": 3}
BROKEN_TASK_COST = 100
STEERABLE_ROLES = ("object_id", "destination", "amount")
AGENT_NAME = "support-agent"


@dataclass
class Problem:
    tools: list[str]
    legs: dict[str, dict[str, bool]]
    constraints: dict[str, list[dict[str, Any]]]
    fully_bound: dict[str, bool]
    tasks: dict[str, list[str]]  # task -> tools used, catalog order
    scoped_ok: dict[tuple[str, str], bool] = field(default_factory=dict)  # (task, tool)

    def allowed_modes(self, tool: str) -> tuple[str, ...]:
        return MODES if self.constraints[tool] else tuple(m for m in MODES if m != "scoped")

    def x_active(self, tool: str, mode: str) -> bool:
        return self.legs[tool]["X"] and (mode == "allow" or (mode == "scoped" and not self.fully_bound[tool]))

    def task_legs(self, task: str) -> list[str]:
        used = self.tasks[task]
        return [leg for leg in ("U", "S", "X") if any(self.legs[t][leg] for t in used)]


def build_problem(catalog: list[dict[str, Any]], invariants: list[dict[str, Any]],
                  sessions: list[dict[str, Any]]) -> Problem:
    tools = [t["tool"] for t in catalog]
    legs = {t["tool"]: t["legs"] for t in catalog}
    constraints: dict[str, list[dict[str, Any]]] = {t: [] for t in tools}
    for inv in invariants:
        if inv["status"] == "accepted" and inv["tool"] in constraints:
            constraints[inv["tool"]].append(
                {"arg": inv["arg"], "op": inv["op"], "ctx": inv["ctx_path"], "invariant": inv["id"]})
    fully_bound = {}
    for t in catalog:
        bound = {c["arg"] for c in constraints[t["tool"]]}
        steerable = {a["name"] for a in t["args"] if a["role"] in STEERABLE_ROLES}
        fully_bound[t["tool"]] = bool(constraints[t["tool"]]) and steerable <= bound

    used: dict[str, set[str]] = defaultdict(set)
    scoped_ok: dict[tuple[str, str], bool] = {}
    for session in sessions:
        if session["label"] != "legit":
            continue
        task = session["task_id"]
        for call in session["calls"]:
            tool = call["tool"]
            if tool not in legs:
                continue
            used[task].add(tool)
            holds = all(_check_constraint(c, call["args"], session["context"]) is None for c in constraints[tool])
            scoped_ok[(task, tool)] = scoped_ok.get((task, tool), True) and holds
    tasks = {task: [t for t in tools if t in used[task]] for task in sorted(used)}
    return Problem(tools, legs, constraints, fully_bound, tasks, scoped_ok)


# -- evaluation shared by both methods ---------------------------------------------------------


def _preserved(problem: Problem, task: str, modes: dict[str, str]) -> bool:
    active = 0
    for leg in ("U", "S"):
        active += any(problem.legs[t][leg] for t in problem.tasks[task])
    active += any(problem.x_active(t, modes[t]) for t in problem.tasks[task])
    for tool in problem.tasks[task]:
        if modes[tool] == "deny":
            return False
        if modes[tool] == "scoped" and not problem.scoped_ok.get((task, tool), True):
            return False
    return active <= 2


def _objective(problem: Problem, modes: dict[str, str]) -> int:
    broken = sum(not _preserved(problem, k, modes) for k in problem.tasks)
    return BROKEN_TASK_COST * broken + sum(MODE_COST[m] for m in modes.values())


# -- exhaustive fallback ------------------------------------------------------------------------


def _solve_exhaustive(problem: Problem, assumptions: list[tuple[str, str]]) -> dict[str, str] | None:
    best, best_cost = None, None
    choices = [problem.allowed_modes(t) for t in problem.tools]
    for combo in itertools.product(*choices):
        modes = dict(zip(problem.tools, combo))
        if not _assumptions_hold(problem, modes, assumptions):
            continue
        cost = _objective(problem, modes)
        if best_cost is None or cost < best_cost:
            best, best_cost = modes, cost
    return best


def _assumptions_hold(problem: Problem, modes: dict[str, str], assumptions: list[tuple[str, str]]) -> bool:
    for kind, name in assumptions:
        if kind == "preserve" and not _preserved(problem, name, modes):
            return False
        if kind == "no_approval" and modes[name] == "approval":
            return False
    return True


# -- CP-SAT -------------------------------------------------------------------------------------


def _solve_cp_sat(problem: Problem, assumptions: list[tuple[str, str]]) -> tuple[str, dict[str, str] | None, list[int]]:
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    x = {t: {m: model.new_bool_var(f"{t}:{m}") for m in MODES} for t in problem.tools}
    for t in problem.tools:
        model.add_exactly_one(x[t].values())
        if "scoped" not in problem.allowed_modes(t):
            model.add(x[t]["scoped"] == 0)

    preserved = {}
    for task, used in problem.tasks.items():
        keep = preserved[task] = model.new_bool_var(f"preserve:{task}")
        for t in used:
            model.add_implication(keep, x[t]["deny"].Not())
            if not problem.scoped_ok.get((task, t), True):
                model.add_implication(keep, x[t]["scoped"].Not())
        x_leg = model.new_bool_var(f"X:{task}")
        for t in used:
            if problem.legs[t]["X"]:
                model.add_implication(x[t]["allow"], x_leg)
                if not problem.fully_bound[t]:
                    model.add_implication(x[t]["scoped"], x_leg)
        constant_legs = sum(any(problem.legs[t][leg] for t in used) for leg in ("U", "S"))
        model.add(x_leg + constant_legs <= 2).only_enforce_if(keep)

    model.minimize(
        sum(BROKEN_TASK_COST * (1 - keep) for keep in preserved.values())
        + sum(MODE_COST[m] * x[t][m] for t in problem.tools for m in MODES)
    )
    literals = []
    for kind, name in assumptions:
        literals.append(preserved[name] if kind == "preserve" else x[name]["approval"].Not())
    if literals:
        model.add_assumptions(literals)

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1  # deterministic
    status = solver.solve(model)
    name = solver.status_name(status)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        modes = {t: next(m for m in MODES if solver.value(x[t][m])) for t in problem.tools}
        return name, modes, []
    core: list[int] = []
    if status == cp_model.INFEASIBLE and literals:
        indices = {lit.index: pos for pos, lit in enumerate(literals)}
        core = sorted(indices[i] for i in solver.sufficient_assumptions_for_infeasibility() if i in indices)
    return name, None, core


# -- conflicts ----------------------------------------------------------------------------------


def _minimal_core(problem: Problem, method: str) -> list[tuple[str, str]]:
    assumptions = [("preserve", k) for k in problem.tasks] + [("no_approval", t) for t in problem.tools]

    def feasible(subset: list[tuple[str, str]]) -> bool:
        if method == "exhaustive":
            return _solve_exhaustive(problem, subset) is not None
        return _solve_cp_sat(problem, subset)[1] is not None

    if method == "exhaustive":
        if feasible(assumptions):
            return []
        core = list(assumptions)
    else:
        _, modes, idx = _solve_cp_sat(problem, assumptions)
        if modes is not None:
            return []
        core = [assumptions[i] for i in idx] or list(assumptions)
    for literal in list(core):  # deletion-based shrinking to a minimal core
        trial = [c for c in core if c != literal]
        if not feasible(trial):
            core = trial
    return core


def _split_partition(problem: Problem) -> list[list[str]] | None:
    used = [t for t in problem.tools if any(t in tools for tools in problem.tasks.values())]
    side_a = [t for t in used if problem.legs[t]["U"]
              or (problem.legs[t]["X"] and problem.fully_bound[t] and not problem.legs[t]["S"])]
    side_b = [t for t in used if t not in side_a]

    def legs_ok(side: list[str]) -> bool:
        active = sum(any(problem.legs[t][leg] for t in side) for leg in ("U", "S"))
        active += any(problem.legs[t]["X"] and not problem.fully_bound[t] for t in side)
        return active <= 2

    return [side_a, side_b] if side_a and side_b and legs_ok(side_a) and legs_ok(side_b) else None


def _conflicts(problem: Problem, core: list[tuple[str, str]], modes: dict[str, str]) -> list[dict[str, Any]]:
    tools = [name for kind, name in core if kind == "no_approval"]
    tasks = [name for kind, name in core if kind == "preserve"]
    if not tools or not tasks:
        return []
    partition = _split_partition(problem)
    out = []
    for task in tasks:
        fixes: list[dict[str, Any]] = [{"type": "approval_edge", "tool": t} for t in tools]
        if partition:
            fixes.append({"type": "split_agent", "partition": partition})
        conflict: dict[str, Any] = {"task": task, "legs": problem.task_legs(task), "core": tools, "fixes": fixes}
        if all(modes.get(t) == "approval" for t in tools):
            conflict["resolved_by"] = "approval_edge"
        out.append(conflict)
    return out


def _legs_per_session(problem: Problem, modes: dict[str, str]) -> dict[str, Any]:
    kept = [k for k in problem.tasks if _preserved(problem, k, modes)]
    out: dict[str, Any] = {}
    for leg in ("U", "S", "X"):
        present = any(problem.legs[t][leg] for k in kept for t in problem.tasks[k])
        if leg == "X" and present:
            active = any(problem.x_active(t, modes[t]) for k in kept for t in problem.tasks[k])
            out[leg] = True if active else "bounded"
        else:
            out[leg] = present
    return out


def optimize(
    catalog: list[dict[str, Any]],
    invariants: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    *,
    method: str = "cp-sat",
    agent: str = AGENT_NAME,
) -> dict[str, Any]:
    """Return a policy document (contracts/policy.schema.json)."""
    problem = build_problem(catalog, invariants, sessions)
    if method == "exhaustive":
        modes = _solve_exhaustive(problem, [])
        status = "OPTIMAL" if modes is not None else "INFEASIBLE"
    elif method == "cp-sat":
        status, modes, _ = _solve_cp_sat(problem, [])
    else:
        raise ValueError(f"unknown method {method!r}")
    if modes is None:
        raise RuntimeError(f"optimizer returned {status}")

    tools: dict[str, Any] = {}
    for t in problem.tools:
        rule: dict[str, Any] = {"mode": modes[t]}
        if modes[t] in ("scoped", "approval") and problem.constraints[t]:
            rule["constraints"] = problem.constraints[t]
        tools[t] = rule

    core = _minimal_core(problem, method)
    return {
        "agents": [{"name": agent, "tools": tools}],
        "legs_per_session": _legs_per_session(problem, modes),
        "solver": {
            "status": status,
            "method": method,
            "objective": _objective(problem, modes),
            "broken_tasks": [k for k in problem.tasks if not _preserved(problem, k, modes)],
        },
        "conflicts": _conflicts(problem, core, modes),
    }
