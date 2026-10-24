# AgentChainCut

Compile and prove least-privilege policies for MCP-connected AI agents.

**What exists and runs today:** the artifact contracts (JSON Schemas + validated fixtures),
contract helpers in `acc/contracts.py`, the package skeleton and a stub `acc` CLI.
The pipeline itself is not implemented yet.

| Read this | For |
|---|---|
| [`docs/GUIA-EQUIPO.md`](docs/GUIA-EQUIPO.md) | Team onboarding in Spanish, with diagrams: the problem, the idea, roles, how to start |
| [`odd/tasks/agentchaincut.md`](odd/tasks/agentchaincut.md) | Design, contracts, algorithms, evaluation and the T01–T17 task list |

## Workflow

- `main` is the shared base; one branch per task (e.g. `feat/t05-miner`) and a PR back to `main`.
- One Conventional Commit per task; tick the task in `odd/tasks/agentchaincut.md` with evidence.
- Do not change a schema in `contracts/` without telling the team: schemas reject unknown fields.

## Quickstart

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`acc run world/` exists but exits non-zero with "not implemented" until the pipeline lands.

## Contracts

Every pipeline artifact has a JSON Schema (draft 2020-12) in `contracts/` and a small,
mutually consistent fixture for the demo support-agent world in `contracts/fixtures/`.
Code against the fixtures from hour 0; change a schema only in a dedicated PR.

| Artifact | Schema | Fixture | Format |
|---|---|---|---|
| Tool catalog (legs U/S/X) | `catalog.schema.json` | `catalog.json` | JSON array |
| Trace session | `trace.schema.json` | `traces.jsonl` | one session per line |
| Mined invariants | `invariants.schema.json` | `invariants.json` | JSON array |
| Policy | `policy.schema.json` | `policy.yaml` | YAML, validated as JSON |
| Verification report | `verify.schema.json` | `verify.json` | JSON object |
| Proxy decision ledger | `ledger_entry.schema.json` | `ledger.jsonl` | one entry per line, hash-chained |

Helpers (`from acc import contracts`):

- `load_schema(name)`, `validate(name, obj)` — raise `jsonschema.ValidationError` on failure.
- `validate_file(path, schema=None)` — `.json`, `.jsonl` (per line), `.yaml`/`.yml`; the schema
  is inferred from the file name (`catalog*`, `trace*`, `invariants*`, `policy*`, `verify*`, `ledger*`).
- `canonical_json(obj)`, `ledger_hash(prev, entry)`, `verify_ledger(entries)` — ledger chain:
  `hash = sha256(prev + canonical_json(entry without "hash"))`, first `prev` is 64 zeros,
  `args_hash = sha256(canonical_json(args))`.

Fixture numbers (support counts, 200/300 verify totals) are illustrative, not measured.

## Layout

| Path | Owner | Purpose |
|---|---|---|
| `contracts/` | all | schemas + fixtures |
| `acc/` | P2–P4 | pipeline package and `acc` CLI; `acc/export/` policy exporters |
| `world/` | P1 | mock tickets / billing / mail MCP servers |
| `proxy/` | P1 | credential-holding MCP proxy, policy engine, ledger |
| `eval/` | P2, P3 | `crosstenant/`, `agentdojo/`, `baselines/` |
| `api/` | P5 | FastAPI service |
