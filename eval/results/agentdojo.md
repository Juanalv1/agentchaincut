# AgentDojo v1.2 — policy level, within-suite 5-fold

Ground-truth calls of held-out user tasks (utility) and of every injection task inside each held-out user task's session (attacks), checked against a policy computed from the other folds. Trusted context = literals typed by the user in the prompt. No LLM in the loop: **indicative, not comparable one-to-one with published end-to-end numbers.**

| Suite | Attacks allowed automatically ↓ | Attacks held for human approval | Utility (approval = ok) ↑ | Utility (no approval) ↑ |
|---|---|---|---|---|
| workspace | 0.0% (0/560) | 92.9% (520/560) | 85.0% (34/40) | 42.5% (17/40) |
| travel | 48.6% (68/140) | 14.3% (20/140) | 80.0% (16/20) | 80.0% (16/20) |
| banking | 0.0% (0/144) | 97.9% (141/144) | 87.5% (14/16) | 25.0% (4/16) |
| slack | 40.0% (42/105) | 32.4% (34/105) | 95.2% (20/21) | 61.9% (13/21) |
| **all** | **11.6% (110/949)** | 75.3% (715/949) | **86.6% (84/97)** | 51.5% (50/97) |

| Published reference | Attack success | Utility |
|---|---|---|
| No defense (published, end-to-end) | 39.9% | 79.4% |
| Progent, manual policies (published, end-to-end) | 0% | — |
| Progent, LLM-generated policies (published, end-to-end) | 1.0% | 76.3% |

Reading: AgentDojo tasks take recipients and ids from tool outputs (files, channels, emails), so `arg ∈ prompt` rules break on legit work and the miner rejects them. Without trusted session context the optimizer falls back to human approval on external effects, which is where most attacks land. Attacks that still pass run in sessions with no sensitive read (Rule of Two allows U+X without S).
