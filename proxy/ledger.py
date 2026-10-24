"""Append-only, hash-chained decision ledger (owner: P1).

hash = sha256(prev + canonical_json(entry without "hash")); the first prev is 64 zeros
(see acc.contracts). Entries are also appended to a JSONL file when a path is given.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from acc.contracts import GENESIS_HASH, args_hash, ledger_hash, verify_ledger


class Ledger:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.entries: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        if self.path and self.path.exists():
            self.entries = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    @classmethod
    def load(cls, path: str | Path) -> Ledger:
        return cls(path)

    def append(self, session_id: str, tool: str, args: dict[str, Any], decision: str,
               rule: str | None, reason: str, ts: str | None = None) -> dict[str, Any]:
        with self._lock:
            prev = self.entries[-1]["hash"] if self.entries else GENESIS_HASH
            entry: dict[str, Any] = {
                "seq": len(self.entries) + 1,
                "ts": ts or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "session_id": session_id,
                "tool": tool,
                "args_hash": args_hash(args),
                "decision": decision,
                "rule": rule,
                "reason": reason,
                "prev": prev,
            }
            entry["hash"] = ledger_hash(prev, entry)
            self.entries.append(entry)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, sort_keys=True) + "\n")
            return entry

    def verify(self) -> int | None:
        """Index of the first entry that breaks the chain, or None when intact."""
        return verify_ledger(self.entries)
