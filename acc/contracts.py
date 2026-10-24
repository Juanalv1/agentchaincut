"""Load and validate AgentChainCut artifacts against the JSON Schemas in `contracts/`.

Also owns the ledger hash-chain primitives shared by the proxy (writer) and the API (verifier).
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import jsonschema
import yaml

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"
GENESIS_HASH = "0" * 64

SCHEMAS = ("catalog", "trace", "invariants", "policy", "verify", "ledger_entry")

# File-name prefix -> schema name, checked in order (used by validate_file).
_FILE_PREFIXES = (
    ("catalog", "catalog"),
    ("trace", "trace"),
    ("invariants", "invariants"),
    ("policy", "policy"),
    ("verify", "verify"),
    ("ledger", "ledger_entry"),
)


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """Return the parsed schema `contracts/<name>.schema.json`. Raises KeyError if unknown."""
    if name not in SCHEMAS:
        raise KeyError(f"unknown contract schema {name!r}; expected one of {SCHEMAS}")
    path = CONTRACTS_DIR / f"{name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _validator(name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(load_schema(name))


def validate(name: str, obj: Any) -> None:
    """Validate `obj` against schema `name`. Raises jsonschema.ValidationError."""
    error = jsonschema.exceptions.best_match(_validator(name).iter_errors(obj))
    if error is not None:
        raise error


def schema_for_path(path: Path) -> str:
    """Infer the schema name from a file name such as `policy.yaml` or `traces.jsonl`."""
    stem = path.name.lower()
    for prefix, schema in _FILE_PREFIXES:
        if stem.startswith(prefix):
            return schema
    raise ValueError(f"cannot infer contract schema from file name {path.name!r}")


def validate_file(path: str | Path, schema: str | None = None) -> int:
    """Validate a .json, .jsonl (one document per line) or .yaml/.yml file.

    Returns the number of documents validated. Raises jsonschema.ValidationError
    (message prefixed with the file and, for JSONL, the line number) or ValueError.
    """
    path = Path(path)
    name = schema or schema_for_path(path)
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".jsonl":
        count = 0
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            _validate_located(name, json.loads(line), f"{path.name} line {lineno}")
            count += 1
        return count
    if suffix in (".yaml", ".yml"):
        _validate_located(name, yaml.safe_load(text), path.name)
        return 1
    if suffix == ".json":
        _validate_located(name, json.loads(text), path.name)
        return 1
    raise ValueError(f"unsupported contract file type {suffix!r}")


def _validate_located(name: str, obj: Any, where: str) -> None:
    try:
        validate(name, obj)
    except jsonschema.ValidationError as exc:
        exc.message = f"{where}: {exc.message}"
        raise


def canonical_json(obj: Any) -> str:
    """Deterministic JSON used for hashing: sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def args_hash(args: dict[str, Any]) -> str:
    """Ledger `args_hash`: sha256 of the canonical JSON of the call arguments."""
    return sha256_hex(canonical_json(args))


def ledger_hash(prev: str, entry: dict[str, Any]) -> str:
    """sha256(prev + canonical_json(entry without 'hash'))."""
    body = {k: v for k, v in entry.items() if k != "hash"}
    return sha256_hex(prev + canonical_json(body))


def verify_ledger(entries: Iterable[dict[str, Any]]) -> int | None:
    """Return the index of the first entry that breaks the chain, or None if intact."""
    prev = GENESIS_HASH
    for index, entry in enumerate(entries):
        if entry.get("prev") != prev or entry.get("hash") != ledger_hash(prev, entry):
            return index
        prev = entry["hash"]
    return None
