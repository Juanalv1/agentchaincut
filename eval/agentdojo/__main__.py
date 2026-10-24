"""Policy-level AgentDojo evaluation -> eval/results/agentdojo.{json,md}.

    python -m eval.agentdojo [--k 5] [--version v1.2]

Data comes from eval/agentdojo/data (exported once with `.venv-agentdojo/bin/python
eval/agentdojo/export.py`; AgentDojo is MIT-licensed). Published rows are end-to-end numbers
quoted from the Progent paper and are not directly comparable with policy-level results.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.agentdojo.evaluate import evaluate

ROOT = Path(__file__).resolve().parents[2]
PUBLISHED = [
    ("No defense (published, end-to-end)", "39.9%", "79.4%"),
    ("Progent, manual policies (published, end-to-end)", "0%", "—"),
    ("Progent, LLM-generated policies (published, end-to-end)", "1.0%", "76.3%"),
]


def _pct(a: int, n: int) -> str:
    return f"{100 * a / n:.1f}% ({a}/{n})" if n else "n/a"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.agentdojo")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--version", default="v1.2")
    parser.add_argument("--out", default=str(ROOT / "eval" / "results"))
    args = parser.parse_args(argv)
    result = evaluate(args.version, args.k)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "agentdojo.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    t = result["total"]
    lines = [
        f"# AgentDojo {args.version} — policy level, within-suite {args.k}-fold", "",
        "Ground-truth calls of held-out user tasks (utility) and of every injection task inside each held-out "
        "user task's session (attacks), checked against a policy computed from the other folds. Trusted context = "
        "literals typed by the user in the prompt. No LLM in the loop: **indicative, not comparable one-to-one with "
        "published end-to-end numbers.**", "",
        "| Suite | Attacks allowed automatically ↓ | Attacks held for human approval | Utility (approval = ok) ↑ | Utility (no approval) ↑ |",
        "|---|---|---|---|---|",
    ]
    for s in result["suites"]:
        lines.append(f"| {s['suite']} | {_pct(s['attacks_succeeded'], s['attacks_n'])} | "
                     f"{_pct(s['attacks_held'], s['attacks_n'])} | {_pct(s['utility_lenient'], s['utility_n'])} | "
                     f"{_pct(s['utility_strict'], s['utility_n'])} |")
    lines.append(f"| **all** | **{_pct(t['attacks_succeeded'], t['attacks_n'])}** | {_pct(t['attacks_held'], t['attacks_n'])} | "
                 f"**{_pct(t['utility_lenient'], t['utility_n'])}** | {_pct(t['utility_strict'], t['utility_n'])} |")
    lines += ["", "| Published reference | Attack success | Utility |", "|---|---|---|"]
    lines += [f"| {name} | {asr} | {util} |" for name, asr, util in PUBLISHED]
    lines += ["", "Reading: AgentDojo tasks take recipients and ids from tool outputs (files, channels, emails), so "
              "`arg ∈ prompt` rules break on legit work and the miner rejects them. Without trusted session context "
              "the optimizer falls back to human approval on external effects, which is where most attacks land. "
              "Attacks that still pass run in sessions with no sensitive read (Rule of Two allows U+X without S)."]
    (out / "agentdojo.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
