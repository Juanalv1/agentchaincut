"""Held-out variant generator (owner: P3).

Variants come from customers the miner never saw (the held-out half of `split_customers`) and
from a different seed, so a policy that merely memorized training values fails here.
"""

from __future__ import annotations

from typing import Any

from acc.traces import generate_sessions
from world.data import World

HELDOUT_LEGIT = 200
HELDOUT_ABUSE = 300


def heldout_sessions(
    world: World,
    heldout_customers: list[str],
    *,
    n_legit: int = HELDOUT_LEGIT,
    n_abuse: int = HELDOUT_ABUSE,
    seed: int = 1026,
) -> list[dict[str, Any]]:
    return generate_sessions(world, heldout_customers, n_legit=n_legit, n_abuse=n_abuse, seed=seed, prefix="h")
