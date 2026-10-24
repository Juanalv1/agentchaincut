"""Optional Claude access shared by the leg classifier, the LLM-policy baseline and the live agent.

The key is read from ANTHROPIC_API_KEY or from a git-ignored `.env` at the repo root. Requests
send no `temperature` (the current API rejects it); callers cache answers for determinism.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

MODEL = "claude-opus-5-5"
ROOT = Path(__file__).resolve().parents[1]
PRICES = {  # USD per million tokens (input, output)
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
}
USAGE_FILE = ROOT / "eval" / "results" / "llm_usage.json"


class BudgetExceeded(RuntimeError):
    pass


def spent_usd() -> float:
    if not USAGE_FILE.exists():
        return 0.0
    return float(json.loads(USAGE_FILE.read_text(encoding="utf-8")).get("usd", 0.0))


def record_usage(response) -> None:
    """Accumulate token usage and estimated cost across runs; stop at ACC_LLM_BUDGET_USD."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    data = json.loads(USAGE_FILE.read_text(encoding="utf-8")) if USAGE_FILE.exists() else {}
    if "by_model" not in data:  # migrate the single-model format
        legacy = {k: data.get(k, 0) for k in ("calls", "input_tokens", "output_tokens")}
        data = {"by_model": {data.get("model", MODEL): legacy} if legacy["calls"] else {}}
    model = getattr(response, "model", None) or MODEL
    row = data["by_model"].setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
    row["calls"] += 1
    row["input_tokens"] += usage.input_tokens or 0
    row["output_tokens"] += usage.output_tokens or 0
    total = 0.0
    for name, r in data["by_model"].items():
        price_in, price_out = PRICES.get(name, PRICES[MODEL])
        r["usd"] = round(r["input_tokens"] / 1e6 * price_in + r["output_tokens"] / 1e6 * price_out, 4)
        total += r["usd"]
    data["usd"] = round(total, 4)
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def check_budget() -> None:
    budget = float(os.environ.get("ACC_LLM_BUDGET_USD", "10"))
    if spent_usd() >= budget:
        raise BudgetExceeded(f"LLM budget reached: ${spent_usd():.2f} of ${budget:.2f}")


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Set variables from a KEY=VALUE file without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key, value.strip().strip("'\""))


def available() -> bool:
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def client():  # pragma: no cover - needs network and credentials
    import anthropic

    load_dotenv()
    return anthropic.Anthropic()


def complete(prompt: str, *, max_tokens: int = 2048, effort: str = "low") -> str:  # pragma: no cover
    """One-shot text completion with the server-side refusal fallback enabled."""
    check_budget()
    response = client().beta.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": effort},
        messages=[{"role": "user", "content": prompt}],
    )
    record_usage(response)
    if response.stop_reason == "refusal":
        raise RuntimeError("request refused")
    return "".join(block.text for block in response.content if block.type == "text")
