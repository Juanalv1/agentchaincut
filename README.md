# AgentChainCut

**Least privilege for AI agents, computed and proven before you turn them on.**

## Why this matters

Enterprise agent platforms give agents org-wide or user-wide permissions while they read
untrusted content. Each time this was found, it was fixed by hand, one case at a time, after the fact:

- **Salesforce Agentforce "ForcedLeak"** (Noma Security, Sep 2025, CVSS 9.4): hidden instructions
  in a Web-to-Lead form made the agent exfiltrate CRM data; the fix was a hand-maintained Trusted
  URL allowlist. [source](https://thehackernews.com/2025/09/salesforce-patches-critical-forcedleak.html)
- **ServiceNow Now Assist** (AppOmni, Nov 2025): with default settings, planted text made agents
  copy data and modify records with the privileges of the user who started the interaction.
  [source](https://thehackernews.com/2025/11/servicenow-ai-agents-can-be-tricked.html)
- **GitHub MCP** (Invariant Labs, May 2025): a public issue made the agent read private repos and
  leak them through a PR in a public repo. [source](https://invariantlabs.ai/blog/mcp-github-vulnerability)

The user is the platform or security team about to connect an agent to its tools, asking: *what
is the minimum this agent needs, and how do I prove it cannot leak with that?* People do not
write least privilege correctly by hand — that is why cloud IAM ships policy generators from
observed usage (e.g. AWS IAM Access Analyzer). Agents are harder: the right permission depends on
the session (this ticket, this repo, this customer), platform defaults are broad, and you must
prove the cut does not break real work.

AgentChainCut computes the policy **once, offline**, from traces of legitimate work: it mines
formal relations that legitimate work always follows (`github.create_pr.repo == task.repo`,
`mail.send.to == ticket.customer.email`, `invoice_id ∈ customer.invoice_ids`), picks the
narrowest policy with a CP-SAT solver under Meta's Agents Rule of Two, and verifies it on unseen
sessions and attacks. A credential-holding MCP proxy then evaluates those rules against **each
session's trusted context** and writes every decision to a hash-chained ledger. The rules are not
natural language and no LLM decides at runtime; humans only see a natural-language explanation.
Fixed "minimum permission" lists are not enough: a static allowlist let **58.3%** of attacks
through in our cross-tenant benchmark (175/300).

Our worked example is a support agent: a polite poisoned ticket made live Claude agents read
another customer's invoice in **45/46** unprotected runs; through the proxy, **0/114** runs
disclosed foreign data or refunded a foreign invoice (details below).

Honest limits: ForcedLeak exfiltrated through an image URL in the model's *output*, not a tool
call, so this proxy as-is would not have stopped it — we cite it to show the problem (it breaks
the Rule of Two), not as a block we claim. Free-form SQL arguments (the Supabase MCP case) and
server-side bugs are out of scope.

## What runs today (one command per claim)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                               # 158 tests
```

| Claim | Command | Result (seed 26) |
|---|---|---|
| Full pipeline: discover → classify → traces → mine → CP-SAT → verify → export | `acc run world/ --out artifacts` | ~1 s, every artifact schema-validated |
| The abuse path exists before the policy and is refused after it | same, see `artifacts/reachability.json` | before: allowed (victim invoice reaches `attacker@evil.test`); after: refused at `billing.invoice_read` |
| Mined rules bind arguments to the session; bad candidates are rejected with a reason | `artifacts/invariants.json` | 6 accepted; rejected: constant, distinct<5, untrusted_ctx, coincidental ×2 |
| The solver keeps all legit work and explains its one conflict | `artifacts/policy.yaml` | OPTIMAL, 0 broken tasks; `refund_request` needs U+S+X → human approval on `billing.refund` (or split the agent) |
| Held-out customers pass, attacks are blocked | `artifacts/verify.json` | 200/200 legit, 300/300 abuse blocked, 0 false denies (measured) |
| Cross-tenant benchmark vs baselines | `python -m eval.crosstenant` | attack success: none 100%, taint-only 33.3% (and 17% false denies), static allowlist 58.3%, **AgentChainCut 0.0%** with 100% utility (n=300/200); LLM-written policy (`claude-opus-5-5`, stratified n=24): 0% attacks but 66.7% utility |
| AgentDojo, policy level | `python -m eval.agentdojo` | 11.6% of attacks pass automatically, 75.3% wait for approval, utility 86.6% counting approvals — see the honest reading in `eval/results/agentdojo.md` |
| Enforcing proxy over MCP stdio | `python -m proxy --policy artifacts/policy.yaml` | denied tools are not even advertised; every decision is ledgered |
| API + live demo endpoints + SSE | `python -m api` | `POST /live/attack`, `GET /events`, `GET /ledger/verify`, … |
| Dashboard (static, offline replay or live) | `cd web && npm install && npm run sync && npm run build` | `npx serve web/out` |
| Exports | `artifacts/export/` | Claude Code PreToolUse hook, Progent-style JSON, Assay-style YAML |
| Live Claude agents, same poisoned ticket, unprotected vs proxy (English, neutral Spanish `-es`, Venezuelan street slang `-ve`) | `python -m eval.live --runs 5 --attack subtle-ve --model claude-haiku-4-5`; offline re-score of the recorded runs, no API calls: `python -m eval.live rescore` | Polite confused-deputy ticket, unprotected: every model we tried read another customer's invoice into its context in **45/46 runs** (Haiku 4.5 15/15, Haiku 5.5 15/15, Sonnet 5.5 10/10, Opus 5.5 5/6), and Haiku 4.5 disclosed its amount to the attacker in a customer-visible ticket note in **14/15**; its emails went to the invoice owner's own address, which we do not count as exfiltration. Malicious ticket (Haiku 4.5 and 5.5 only, n=30): 14/30 foreign reads, 4/30 note disclosures, **2 refunds executed on another customer's invoice**. Obvious ticket (n=38): 0 reads, 0 disclosures. Through the proxy, all styles (n=114): **0 disclosures, 0 foreign refunds**, customer answered 113/114; 0 foreign reads, which the mined `invoice_read` ownership rule (`inv-2` in the transcripts) enforces by construction. Coverage: n=5 per cell except Opus 5.5 (n=3); Sonnet and Opus ran only obvious (English), subtle and subtle-ve. Metric history: 88cea4f switched the headline from leaks to foreign reads because the old leak count flagged replies that only named the victim id or mailed the customer their own invoice; the v2 disclosure metric (`leaked_v2`, notes counted, mail to the data owner excluded) sits next to the unchanged v1 `leaked` in `eval/results/live/summary.json` |

LLM runs need `ANTHROPIC_API_KEY` (env or git-ignored `.env`) and `pip install -e ".[llm]"`; answers
are cached under `eval/results/` and spend is tracked in `eval/results/llm_usage.json` with a
budget stop (`ACC_LLM_BUDGET_USD`, default 10).

## How it works

```
offline (file → file)                                                live
MCP servers → discover → classify U/S/X → traces → mine → CP-SAT → verify → export
                                                                  │ policy.yaml
agent ──MCP──▶ PROXY (credentials, session context, policy engine, ledger) ──▶ MCP servers
                                  │ SSE
                          FastAPI ─┴─▶ dashboard
```

- **Rule of Two:** a session should not combine untrusted input (U), sensitive data (S) and an
  external effect (X). U and S stay present when used; X is neutralized by human approval or by
  binding every steerable argument (object id, destination, amount) to trusted session context.
- **The LLM never grants permissions.** It may label unknown tools (cached); the policy comes
  from mined rules and the solver.
- **Trusted context comes from the backend,** fetched by the proxy at session start, never from
  agent text. Unknown session, unknown tool or engine error → deny.
- **Every number** comes from a deterministic check, carries its n and a
  `measured | assumed | not-measured` label.

Declared limits: free-form SQL arguments, server-side bugs, the residual channels listed in
`verify.json` (lower bound), and a synthetic world modeled on Zendesk / Stripe / Gmail-like APIs.

## Repository

| Path | What |
|---|---|
| `contracts/` | JSON Schemas for every artifact + fixtures (`acc/contracts.py` helpers) |
| `acc/` | pipeline: `discover`, `classify`, `traces`, `miner`, `optimizer`, `reachability`, `variants`, `verifier`, `policy_engine`, `pipeline`, `export/`, CLI `acc` |
| `world/` | seeded support world (200 customers) and MCP servers (mcp 2.x `MCPServer`) |
| `proxy/` | credential-holding MCP proxy and hash-chained ledger |
| `eval/` | `baselines/`, `crosstenant/`, `agentdojo/`, `live/`, `results/` |
| `api/` | FastAPI service |
| `web/` | Next.js + React Flow dashboard |
| `docs/GUIA-EQUIPO.md` | team onboarding (Spanish) |
| `odd/tasks/agentchaincut.md` | design, contracts, tasks T01–T18 and the work log |

## Workflow

- Everyone works directly on `main`: no feature branches, no PRs. `git pull --rebase --autostash`
  before a change, commit and `git push` after it (see `CLAUDE.md`).
- Conventional Commits ending with a `Status: pending | in-progress | done` trailer; tick the task
  in `odd/tasks/agentchaincut.md` with evidence.
- Do not change a schema in `contracts/` without telling the team: schemas reject unknown fields.
