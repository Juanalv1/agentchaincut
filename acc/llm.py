"""Optional Claude access shared by the leg classifier, the LLM-policy baseline and the live agent.

The key is read from ANTHROPIC_API_KEY or from a git-ignored `.env` at the repo root. Requests
send no `temperature` (the current API rejects it); callers cache answers for determinism.
"""

from __future__ import annotations

import os
from pathlib import Path

MODEL = "claude-opus-5-5"
ROOT = Path(__file__).resolve().parents[1]


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
    response = client().beta.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": effort},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("request refused")
    return "".join(block.text for block in response.content if block.type == "text")
