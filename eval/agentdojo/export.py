"""Export AgentDojo suites (tools, user-task prompts, ground-truth calls, injection ground truth)
to JSON so the policy-level evaluation runs in the main environment without agentdojo installed.

Run with the separate AgentDojo env (Python 3.12):
    .venv-agentdojo/bin/python eval/agentdojo/export.py --version v1.2
"""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
from typing import Any

from agentdojo.task_suite.load_suites import get_suites

OUT = Path(__file__).resolve().parent / "data"


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


def _calls(calls: list[Any]) -> list[dict[str, Any]]:
    return [{"function": c.function, "args": _jsonable(dict(c.args))} for c in calls]


def export(version: str) -> dict[str, Any]:
    out: dict[str, Any] = {"benchmark_version": version, "suites": {}}
    for name, suite in get_suites(version).items():
        env = suite.load_and_inject_default_environment({})
        tools = []
        for tool in suite.tools:
            params = tool.parameters.model_json_schema() if hasattr(tool.parameters, "model_json_schema") else {}
            tools.append({"name": tool.name, "description": (tool.description or "").strip().split("\n")[0],
                          "parameters": params})
        user_tasks = []
        for task_id, task in suite.user_tasks.items():
            user_tasks.append({"id": task_id, "prompt": task.PROMPT,
                               "ground_truth": _calls(task.ground_truth(env.model_copy(deep=True)))})
        injection_tasks = []
        for task_id, task in suite.injection_tasks.items():
            injection_tasks.append({"id": task_id, "goal": task.GOAL,
                                    "ground_truth": _calls(task.ground_truth(env.model_copy(deep=True)))})
        out["suites"][name] = {"tools": tools, "user_tasks": user_tasks, "injection_tasks": injection_tasks}
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1.2")
    args = parser.parse_args()
    data = export(args.version)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"agentdojo-{args.version}.json"
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    counts = {k: (len(v["user_tasks"]), len(v["injection_tasks"])) for k, v in data["suites"].items()}
    print(f"wrote {path} {counts}")
