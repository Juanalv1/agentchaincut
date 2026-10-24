"""Rule-of-Two leg classifier (owner: P2).

Order: manual override -> MCP hints -> verb heuristic -> cached LLM -> default sink (X=true).
The LLM only labels tools; it never grants permissions, and any unusable answer falls back
to the fail-closed sink default.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from acc import llm as claude
from acc.contracts import canonical_json

READ_VERBS = {"get", "read", "list", "search", "fetch", "find", "lookup", "query", "show", "view", "check"}
WRITE_VERBS = {
    "send", "add", "create", "update", "delete", "remove", "refund", "pay", "post", "write",
    "set", "close", "transfer", "upload", "publish", "reply", "forward", "charge", "cancel",
    "reschedule", "append", "share", "schedule", "reserve", "invite", "book",
}
SENSITIVE_WORDS = {
    "invoice", "billing", "payment", "customer", "account", "card", "salary", "ssn", "medical",
    "password", "secret", "token", "bank", "iban", "balance", "transaction", "transactions", "payroll",
    "user", "contact", "contacts", "inbox", "emails", "files", "file", "calendar",
}
UNTRUSTED_WORDS = {
    "ticket", "tickets", "message", "messages", "inbox", "web", "page", "webpage", "comment", "issue",
    "review", "reviews", "feedback", "email", "emails", "file", "files", "transactions", "channel",
}

LLM_MODEL = claude.MODEL
_LEGS_SINK = {"U": False, "S": False, "X": True}


def load_overrides(path: str | Path) -> dict[str, dict[str, Any]]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _words(tool: str) -> set[str]:
    return {w for w in re.split(r"[._\-]", tool.lower()) if w}


class LLMClassifier:
    """Cached LLM fallback. `complete(prompt) -> str` is injectable for tests and offline runs."""

    def __init__(self, cache_path: str | Path, complete: Callable[[str], str] | None = None) -> None:
        self.cache_path = Path(cache_path)
        self._complete = complete or claude.complete
        self._cache: dict[str, Any] = (
            json.loads(self.cache_path.read_text(encoding="utf-8")) if self.cache_path.exists() else {}
        )

    def legs(self, tool: dict[str, Any]) -> tuple[dict[str, bool], str] | None:
        key = hashlib.sha256(
            canonical_json({k: tool.get(k) for k in ("tool", "description", "annotations", "args")}).encode()
        ).hexdigest()
        if key not in self._cache:
            try:
                self._cache[key] = self._complete(_prompt(tool))
            except Exception:  # network, auth or refusal: no label, caller falls back to the sink
                return None
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache, indent=2, sort_keys=True), encoding="utf-8")
        return _parse_llm(self._cache[key])


def _prompt(tool: dict[str, Any]) -> str:
    return (
        "Classify this MCP tool for the Agents Rule of Two. Answer with JSON only: "
        '{"U": bool, "S": bool, "X": bool, "rationale": str}. '
        "U = its output can contain text written by outsiders (untrusted input). "
        "S = it reads sensitive or private data. "
        "X = it changes state or communicates outside the agent.\n\n"
        f"Tool: {json.dumps(tool, sort_keys=True)}"
    )


def _parse_llm(text: str) -> tuple[dict[str, bool], str] | None:
    try:
        match = re.search(r"\{.*\}", text, re.S)
        data = json.loads(match.group(0) if match else text)
        legs = {leg: bool(data[leg]) for leg in ("U", "S", "X")}
        return legs, f"LLM ({LLM_MODEL}, cached): {data.get('rationale', 'no rationale')}"
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def classify_tool(
    tool: dict[str, Any],
    overrides: dict[str, dict[str, Any]] | None = None,
    llm: LLMClassifier | None = None,
) -> dict[str, Any]:
    """Return a catalog entry (contracts/catalog.schema.json) for one discovered tool."""
    name = tool["tool"]
    hints = tool.get("annotations") or {}
    words = _words(name)
    sensitive = bool(words & SENSITIVE_WORDS)

    if overrides and name in overrides:
        legs, source = dict(overrides[name]["legs"]), "manual"
        rationale = overrides[name]["rationale"]
    elif "readOnlyHint" in hints:
        source = "mcp_hint"
        if hints["readOnlyHint"]:
            untrusted = bool(hints.get("openWorldHint"))
            legs = {"U": untrusted, "S": sensitive, "X": False}
            rationale = "readOnlyHint=true" + (
                "; openWorldHint=true, so its output carries untrusted outside text" if untrusted else ""
            ) + ("; name refers to sensitive records" if sensitive else "")
        else:
            legs = {"U": False, "S": False, "X": True}
            rationale = "readOnlyHint=false" + (
                "; destructiveHint=true" if hints.get("destructiveHint") else ""
            ) + ("; openWorldHint=true" if hints.get("openWorldHint") else "") + "; it changes state outside the agent"
    elif words & WRITE_VERBS:
        legs, source = {"U": False, "S": False, "X": True}, "heuristic"
        rationale = f"Write verb {sorted(words & WRITE_VERBS)[0]!r}; classified as an external sink."
    elif words & READ_VERBS:
        untrusted = bool(words & UNTRUSTED_WORDS)
        legs, source = {"U": untrusted, "S": sensitive, "X": False}, "heuristic"
        rationale = f"Read verb {sorted(words & READ_VERBS)[0]!r}" + (
            "; reads outside-authored content" if untrusted else ""
        ) + ("; name refers to sensitive records" if sensitive else "")
    else:
        labelled = llm.legs(tool) if llm is not None else None
        if labelled is not None:
            (legs, rationale), source = labelled, "llm"
        else:
            legs, source = dict(_LEGS_SINK), "heuristic"
            rationale = "Unknown verb and no usable label; default to external sink (fail-closed)."

    entry: dict[str, Any] = {
        "tool": name,
        "server": tool["server"],
        "description": tool.get("description", ""),
        "args": tool.get("args", []),
        "legs": legs,
        "annotations": {k: v for k, v in hints.items() if k in (
            "title", "readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")},
        "source": source,
        "rationale": rationale,
    }
    return entry


def classify(
    tools: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]] | None = None,
    llm: LLMClassifier | None = None,
) -> list[dict[str, Any]]:
    return [classify_tool(tool, overrides, llm) for tool in tools]
