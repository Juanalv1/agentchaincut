"""Claude Code PreToolUse hook export.

The generated script embeds the policy and decides with the same `acc.policy_engine` the proxy
uses, so it needs this package importable (`pip install -e .` or PYTHONPATH). The trusted
session context is read from the JSON file named by `ACC_SESSION_CONTEXT`, written by the
backend when the session starts; without it every scoped call is denied (fail-closed).

Register it in `.claude/settings.json`:
    {"hooks": {"PreToolUse": [{"matcher": "mcp__.*", "hooks": [
        {"type": "command", "command": "python /path/to/acc_hook.py"}]}]}}
"""

from __future__ import annotations

import json
from typing import Any

_TEMPLATE = '''#!/usr/bin/env python3
"""AgentChainCut PreToolUse hook (generated). Decides MCP tool calls with the computed policy."""
import json
import os
import sys

from acc.policy_engine import check

POLICY = json.loads({policy!r})
PROXY_SERVER = "acc"
SERVERS = {{name.split(".", 1)[0] for agent in POLICY["agents"] for name in agent["tools"]}}
DECISIONS = {{"allow": "allow", "deny": "deny", "approval": "ask"}}


def policy_tool(tool_name):
    """mcp__<server>__<tool> or mcp__acc__<server>__<tool> -> <server>.<tool>; None if not ours."""
    if not tool_name.startswith("mcp__"):
        return None
    parts = tool_name[len("mcp__"):].split("__")
    if parts and parts[0] == PROXY_SERVER:
        parts = parts[1:]
    if len(parts) != 2 or parts[0] not in SERVERS:
        return None
    return parts[0] + "." + parts[1]


def load_context():
    path = os.environ.get("ACC_SESSION_CONTEXT")
    if not path:
        return {{}}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {{}}


def main():
    payload = json.load(sys.stdin)
    tool = policy_tool(payload.get("tool_name", ""))
    if tool is None:
        return 0  # not governed by this policy: let Claude Code decide
    decision = check(POLICY, tool, payload.get("tool_input") or {{}}, load_context())
    print(json.dumps({{"hookSpecificOutput": {{
        "hookEventName": "PreToolUse",
        "permissionDecision": DECISIONS[decision.decision],
        "permissionDecisionReason": "AgentChainCut " + str(decision.rule) + ": " + decision.reason,
    }}}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def export_hook(policy: dict[str, Any]) -> str:
    return _TEMPLATE.format(policy=json.dumps(policy, sort_keys=True))
