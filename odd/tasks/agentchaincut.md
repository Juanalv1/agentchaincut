# AgentChainCut — Feature Document

> **First version (v1).** Everything here (scope, contracts, algorithms, evaluation, demo, task
> split) is an initial proposal. The team owns it and is free to revise any part to maximize the
> result; record meaningful changes in Progress so everyone stays aligned.

> Compile and prove least-privilege policies for MCP-connected AI agents.
> Platanus Hack 26 Caracas · AI Security track · Status: **design, not started**

## Objective

Given an AI agent wired to MCP tools, compute the least-privilege policy that blocks
abuse paths (including cross-tenant / confused-deputy abuse) while provably keeping the
agent's legitimate work running — and enforce it in a proxy the agent cannot bypass.

## Problem

Agents run with credentials that legitimately reach every tenant (support agents,
`service_role` keys). The backend sees an authorized operator and cannot tell which
customer *this session* is about. Existing defenses either:

- write rules by hand (Roxy, Progent-manual, Sentinel) — static lists cannot bind an
  argument to the current session, so "send customer A's invoice to customer B" passes;
- ask an LLM at runtime (Consentinel, Progent-LLM, Conseca) — non-deterministic and
  fed by tool output that can be injected;
- block everything untrusted (Ikarus / CaMeL-style taint) — breaks legitimate flows
  such as "reply to the ticket's customer".

## Why

- Meta's Agents Rule of Two: an agent session should hold at most two of
  {untrusted input, sensitive data, external effect}. Nobody checks or optimizes for it.
- Prompt injection is unsolved; per-try success is low on frontier models but rises with
  attempts (33–63% at 10–100 tries in published red-teaming). Safety must come from the
  permission layer, not from the model's behavior — so value does not shrink as models improve.
- No previous Platanus AI Security project ran a standard benchmark or tackled
  cross-tenant isolation.

## Scope

**In:** mock business world (tickets, billing, mail) as MCP servers; trace generation;
tool classification; relational invariant mining; Rule-of-Two CP-SAT optimizer with
conflict reports; held-out verification; reachability proof; credential-holding MCP proxy;
hash-chained decision ledger; exports (Claude Code PreToolUse hook, Progent-style JSON,
Assay/AgentPerms-style YAML); cross-tenant benchmark with baselines; AgentDojo evaluation;
dashboard; live agent run; public deploy; submission files.

**Out:** real ERP integration; free-form SQL arguments (declared limitation, Supabase case);
server-side bugs (Asana case — motivation only); HTTP/SSE MCP transports beyond what the
demo needs; multi-agent orchestration.

## Constraints

- LLM may classify tools and explain findings; **it never grants permissions**.
- Proxy is **fail-closed**: unknown session, unknown tool, engine error → deny.
- Trusted context comes only from the backend (fetched by the proxy at session start),
  never from agent-supplied text.
- Every headline number must come from a deterministic check and be labeled
  `measured | assumed | not-measured`, with `n` per cell.
- Code reuse from other Platanus repos only where licensed (Vibefence is MIT); otherwise ideas only.
- Artifacts (code, docs, UI copy) in English.

## Architecture

```
            ┌──────────── offline pipeline (pure file → file) ─────────────┐
 MCP servers → discover → classify → traces → mine → optimize → verify → export
                (catalog)  (legs)    (jsonl)  (invariants) (policy) (verify)  (hook/progent/assay)
            └───────────────────────────────────────────────────────────────┘
                                         │ policy.yaml
 agent ──MCP──▶ PROXY (holds creds, session ctx, policy_engine.check, ledger) ──▶ MCP servers
                                         │ SSE events
                              FastAPI ◀──┴──▶ Next.js + React Flow dashboard
 eval/: cross-tenant bench + AgentDojo, baselines: none · taint-only · static-allowlist · LLM-policy
```

### Repository layout

```
agentchaincut/
  contracts/        JSON Schemas for every artifact below + fixtures
  acc/              Python package (CLI: `acc run <world>`)
    discover.py  classify.py  traces.py  miner.py  reachability.py
    optimizer.py verifier.py  variants.py ledger.py
    export/{hook.py,progent.py,assay.py}
  world/            FastMCP servers: tickets, billing, mail + seed data (200 customers)
  proxy/            MCP proxy: session binding, policy_engine.py, ledger writer, SSE
  eval/             crosstenant/, agentdojo/, baselines/
  api/              FastAPI (pipeline runs, artifacts, live run, SSE relay)
  web/              Next.js + React Flow dashboard (works from static artifacts)
  README.md         opens with what runs in production + one command per claim
```

Stack rationale: Python for the core because OR-Tools CP-SAT, AgentDojo and the MCP
Python SDK are Python-native; Next.js + React Flow for the graph-heavy UI.

## Contracts

`catalog.json` — one entry per tool
```json
{"tool":"billing.invoice_read","server":"billing",
 "args":[{"name":"invoice_id","type":"string","role":"object_id"}],
 "legs":{"U":false,"S":true,"X":false},
 "annotations":{"readOnlyHint":true},
 "source":"mcp_hint|heuristic|llm|manual","rationale":"..."}
```
Leg classification order (from Ikarus): MCP `readOnlyHint`/`destructiveHint` → verb
heuristic → LLM (cached, temperature 0) → default to sink (`X=true`). Manual overrides win.

`traces.jsonl` — one session per line
```json
{"session_id":"s-001","task_id":"reply_with_invoice","label":"legit|abuse",
 "context":{"ticket.id":"T-17","ticket.customer.email":"ana@acme.test",
            "ticket.partner_id":"P-42","customer.invoice_ids":["I-9","I-12"]},
 "context_provenance":{"ticket.customer.email":"system"},
 "calls":[{"seq":1,"tool":"billing.invoice_read","args":{"invoice_id":"I-9"},
           "arg_provenance":{"invoice_id":"tool_output:tickets.get#1"}}]}
```

`invariants.json`
```json
{"id":"inv-3","tool":"mail.send","arg":"to","op":"eq|in","ctx_path":"ticket.customer.email",
 "support":37,"distinct":37,"violations":0,
 "status":"accepted|rejected|suggested","reject_reason":"constant|distinct<5|coincidental|untrusted_ctx"}
```

`policy.yaml`
```yaml
agents:
  - name: support-agent
    tools:
      billing.invoice_read: {mode: scoped, constraints: [{arg: invoice_id, op: in, ctx: customer.invoice_ids}]}
      mail.send:            {mode: scoped, constraints: [{arg: to, op: eq, ctx: ticket.customer.email}]}
      billing.refund:       {mode: approval}
      billing.invoice_list_all: {mode: deny}
legs_per_session: {U: true, S: true, X: bounded}
solver: {status: OPTIMAL, objective: 3, broken_tasks: []}
conflicts:
  - task: refund_request
    legs: [U, S, X]
    core: [billing.refund]
    fixes: [{type: approval_edge, tool: billing.refund}, {type: split_agent, partition: [...]}]
```

`verify.json`
```json
{"reachability_before":{"path":["tickets.get","billing.invoice_read","mail.send"],"legs":["U","S","X"]},
 "heldout":{"n":200,"pass":200},"abuse":{"n":300,"blocked":300},
 "false_deny":{"n":200,"count":0},
 "residual":[{"sink":"tickets.add_note","arg":"body","status":"unconstrained","claim":"lower-bound"}],
 "labels":{"heldout":"measured","live":"measured","agentdojo":"measured"}}
```

`ledger.jsonl` — proxy decisions
```json
{"seq":12,"ts":"...","session_id":"s-live-1","tool":"mail.send","args_hash":"...",
 "decision":"deny","rule":"inv-3","reason":"to != ticket.customer.email",
 "prev":"<sha256>","hash":"sha256(prev + canonical_json(entry))"}
```

## Algorithms

**Miner** (Daikon-style, restricted grammar)
- Candidates: for each (tool, arg) × context field: `arg == ctx.field`, `arg ∈ ctx.set`.
- Accept only if: 0 violations over legit traces, ≥5 distinct values, context field has
  `system` provenance, no constants. Otherwise `rejected` with reason (shown in UI).
- Read-side invariants are mandatory (e.g. `invoice_id ∈ customer.invoice_ids`): a
  send-side rule alone does not stop reading another tenant's data.
- Accepted invariants surface as **suggestions** a human approves (Tranquera pattern).
- Traces generated with randomized entities and a fixed seed so coincidental equalities break.

**Optimizer** (OR-Tools CP-SAT)
- Variables: per tool, one-hot mode ∈ {allow, scoped, approval, deny}.
- A `scoped` tool whose attacker-controllable argument (destination / object id) is bound
  by an accepted invariant neutralizes its U or X leg.
- Rule of Two: per session, active legs ≤ 2.
- Task preserved ⇔ every call in its traces is permitted under the chosen modes.
- Objective: `Σ w_task·broken + c_approval·#approval + c_deny·#deny`.
- Infeasible at zero broken tasks → assumption literals +
  `SufficientAssumptionsForInfeasibility` → minimal core → conflict report with two fixes:
  approval on one edge, or split the agent (re-solve over two partitions).
- Fallback if CP-SAT modeling slips: exhaustive search on the demo instance, labeled as such.

**Reachability proof (the "before")**
- NetworkX graph over the catalog: untrusted source → sensitive read → external sink.
  The path is executed directly against the permission layer (scripted tool calls, no LLM),
  showing it is allowed. After the policy, the same calls are refused. No reliance on a
  live prompt injection succeeding.

**Verifier**
- Held-out legit variants: unseen customers/tickets/amounts from templates; checked
  deterministically against the policy.
- Abuse variants: foreign recipient, foreign object id, cross-ticket, injected value in a
  context-looking field (provenance guard).
- Residual-risk search: enumerate allowed-but-unconstrained sink args; report as lower bound.

**Proxy**
- Holds the MCP server credentials; the agent only talks to the proxy.
- `session.start(ticket_id)` → proxy fetches trusted context from the backend.
- Every `tools/call` → `policy_engine.check()` → allow / deny / approval + reason →
  ledger append → SSE event. Same engine used by the verifier and the exports.
- Report per-call latency overhead.

## Evaluation

| Suite | Baselines | Metrics |
|---|---|---|
| Cross-tenant bench (own, modeled on Zendesk/Stripe/Gmail schemas + GitHub-MCP-style case) | none · taint-only (Ikarus-like) · static allowlist (Progent-manual-like) · LLM-generated policy (Progent-LLM-like, same model each run) | attack success, utility, false-deny rate, n, policy variance across N LLM runs |
| AgentDojo (within-suite k-fold over user tasks; ground-truth calls; no LLM in scoring) | published: no defense 39.9% ASR / 79.4% util · Progent-manual 0% · Progent-LLM 1.0% / 76.3% | ASR, utility per suite; labeled "policy-level, indicative vs published end-to-end" |

Declared limits on the results slide: free-form SQL args, server-side bugs, residual
channels found by the residual search, synthetic world.

## Demo (3:00)

1. **0:00–0:20** Split screen: same poisoned ticket against unprotected vs protected agent.
2. **0:20–0:45** Reachability proof: red path U → `invoice_read(any)` → `send(any)`.
3. **0:45–1:25** Traces → invariants (rejected ones struck through with reason) →
   CP-SAT: 0 tasks broken, one conflict resolved with approval on `billing.refund` only.
4. **1:25–2:00** Verify: held-out 200/200 pass, abuse 300/300 blocked; live run blocked
   with reason; ledger tamper button turns the chain red.
5. **2:00–2:30** Results table vs taint-only, static allowlist, LLM-policy, and AgentDojo vs Progent.
6. **2:30–3:00** Exports (hook / Progent / Assay) + line: "Every team builds an LLM
   classifier as a guardrail. We compute least privilege with a solver and prove it."

Offline replay mode for every step; recorded fallback video.

## Positioning (one line each)

- Consentinel — guesses drift with an LLM at runtime; we compile provable invariants.
- Ikarus / CaMeL — taint-only blocks legitimate flows; here is our false-deny rate.
- Roxy — checks hand-written rules with Z3; we derive and minimize the rules.
- Progent — static rules can't bind to the session; LLM rules vary run to run.
- AUDGENTIC — records the crash; we prevent it.
- SUNDER / AgentPerms / Assay / Snyk agent-scan — cut graphs, infer from traces or detect
  flows; none verifies that legitimate work survives, none does relational argument rules.

## Work split (5 people)

| Role | Owns |
|---|---|
| P1 World & enforcement | world/, proxy/, ledger, live agent harness |
| P2 Discovery & external eval | discover, classify, eval/agentdojo |
| P3 Miner & verifier | traces, miner, variants, verifier, reachability, residual search |
| P4 Optimizer & exports | optimizer, conflicts, export/, CLI |
| P5 Product & pitch | web/, api/ wiring, README, submission files, demo, video |

Integration rule: everyone codes against `contracts/` fixtures from hour 0.

## Tasks

Route legend: **inline** = parent session; **delegated** = one bounded writer.

- [x] **T01** Repo skeleton + `contracts/` JSON Schemas + fixtures for every artifact — delegated (2+ files)
- [x] **T02** Mock world: tickets, billing, mail MCP servers (mcp 2.x `MCPServer`) + seed data — inline; commit `f3978d5` on `main`
- [x] **T03** Trace generator (6 legit task types, 8 abuse families, fixed seed, provenance) — inline; on `main`
- [ ] **T04** Discovery + leg classifier (hints → heuristic → cached LLM → sink default) — delegated
- [ ] **T05** Invariant miner with filters, reject reasons, suggestion status — delegated
- [ ] **T06** Reachability prover (before path, scripted calls) — delegated
- [ ] **T07** CP-SAT optimizer + unsat core → conflict report + split-agent re-solve — delegated
- [ ] **T08** Variant generator + verifier + residual-risk search — delegated
- [ ] **T09** Credential-holding proxy, session binding, policy engine, fail-closed, ledger, SSE — delegated
- [ ] **T10** Exports: Claude Code PreToolUse hook, Progent-style JSON, Assay-style YAML — delegated
- [ ] **T11** Cross-tenant benchmark + 4 baselines + results table generator — delegated
- [ ] **T12** AgentDojo within-suite k-fold evaluation — delegated
- [ ] **T13** FastAPI service (pipeline run, artifacts, live run, SSE relay) — delegated
- [ ] **T14** Dashboard: tool graph, invariants, solver/conflicts, verify counters, ledger, results — delegated
- [ ] **T15** Live agent run through proxy (pinned model + prompt, rehearsed, offline replay) — delegated
- [ ] **T16** README (production-first, one command per claim), project-description.md,
      platanus-hack-project.jsonc, 1000×1000 logo, public deploy — delegated
- [ ] **T17** Demo script rehearsal + recorded fallback video — human

Acceptance per task: its contract fixture validates, its unit tests pass, and it runs in
`acc run world/` end to end once integrated. Test-first where a deterministic expected
outcome exists (miner, optimizer, policy engine, verifier, ledger).

## Checks

- `pytest` (core, proxy, eval) green; schema validation of every artifact.
- `acc run world/` produces catalog → policy → verify end to end.
- Ledger verify endpoint detects a tampered entry.
- Results table regenerates from raw runs with `n` and labels.

## Delivery

- Strategy: `ask-on-risk`. Forecast clearly exceeds ~400 authored lines → chained-PR
  strategy to be chosen before the first commit.
- One work-unit commit per task on the feature branch (Conventional Commits).
- Push / PR / merge are team decisions.

## Open questions

- Team repo confirmed: `platanus-hack-26-ve-team-21`. Work happens in `Juanalv1/agentchaincut`
  and is mirrored there with full history before submission.
- Role assignment (P1–P5) is pending; see `docs/GUIA-EQUIPO.md`.

## Progress

- 2026-10-24: design drafted after idea refutation rounds and competitor analysis
  (estimated score ~7.3, own estimate, not independently reviewed). No code yet.
- 2026-10-24: T01 done, commit `4b74719` (`feat(contracts): add repo skeleton, JSON schemas and fixtures`), merged to `main`. Review tier: medium (RDD off); writer self-verification plus parent re-run of `pytest` (49 passed). Route: delegated (writer trigger: 2+ non-trivial files). Evidence: `pytest` RED 38 failed / 11 passed against a NotImplementedError stub, then GREEN 49 passed; `pip install -e .[dev]` incl. ortools 9.15 and mcp 2.3 installed on Windows/Python 3.11. Fixture numbers are illustrative, not measured.

- 2026-10-24: T02 done, commit `f3978d5` on `main`. `world/data.py` seeded backend (200 customers, invoices, tickets, outbox, trusted context with provenance) and `world/servers.py` (tickets/billing/mail on mcp 2.x `MCPServer`; servers built only with the backend service key). Evidence: `tests/test_world.py` RED (ImportError) then GREEN, full suite 60 passed; stdio round trip `python -m world.servers billing` listed tools and read `I-0001`. Packaging now installs `world`, `proxy`, `eval`, `api`; dependency pinned to `mcp>=2.3,<3` because FastMCP was renamed in 2.x. Tool signatures extend the illustrative fixture: `tickets.add_note(author)`, `billing.refund(currency)`.

- 2026-10-24: Team decision (user, verbatim): "todo va a main". Work is committed and pushed straight to `main`; no feature branches or PRs. The README "one branch per task" rule no longer applies.
- 2026-10-24: T03 done. `acc/traces.py`: six legit task types and eight abuse families (`foreign_recipient`, `cross_tenant_recipient`, `foreign_object_id`, `cross_ticket`, `injected_context`, `foreign_refund`, `bulk_exfil`, `excess_refund`); the last call of an abuse trace is the malicious one; `split_customers` gives disjoint training/held-out tenants (120/80). Mutating calls are recorded, not executed. Seeded on purpose so the miner meets every reject reason: `author == agent.id` (constant), `currency == customer.currency` (3 values), `to == ticket.reporter_email` (user provenance), `invoice_id == customer.last_invoice_id` (60% coincidence). Evidence: `tests/test_traces.py` 8 tests, full suite 68 passed. RED was not run separately: the implementation was written before the first test run.

## Next step

Assign roles, then start T02–T05 in parallel against `contracts/fixtures/`, one branch and PR per task.
Team onboarding (Spanish, with diagrams): `docs/GUIA-EQUIPO.md`.
