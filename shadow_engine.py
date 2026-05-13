"""Shadow comparator: mock 'legacy' ranking ignores behaviour score."""

from __future__ import annotations

import random
from typing import Sequence

from models import AllocationResult, UserProfile
from store import ScoreStore


def legacy_sort_key(profile: UserProfile, tie_breaker: float) -> tuple[int, int, float]:
    """Legacy proxy: admin layers + random tie-break only (no behaviour)."""
    return (profile.group_priority, profile.user_priority, tie_breaker)


def rank_legacy(
    store: ScoreStore,
    user_ids: Sequence[str],
    *,
    seed: int | None = None,
) -> list[AllocationResult]:
    if seed is not None:
        random.seed(seed)

    candidates: list[tuple[UserProfile, float]] = []
    for uid in user_ids:
        prof = store.get_profile(uid)
        if prof is None:
            continue
        tb = random.random()
        candidates.append((prof, tb))

    candidates.sort(key=lambda row: legacy_sort_key(row[0], row[1]))

    out: list[AllocationResult] = []
    for rank, (prof, tb) in enumerate(candidates, start=1):
        sk = legacy_sort_key(prof, tb)
        explain = (
            f"[legacy/shadow] rank={rank}: group_priority={prof.group_priority}, "
            f"user_priority={prof.user_priority}, behaviour ignored, tie_breaker={tb:.4f}"
        )
        out.append(
            AllocationResult(user_id=prof.user_id, rank=rank, sort_key=sk, explain=explain)
        )
    return out


def shadow_diff(
    newton_ranks: list[AllocationResult],
    legacy_ranks: list[AllocationResult],
) -> list[dict]:
    """Position deltas keyed by user_id."""
    new_pos = {r.user_id: r.rank for r in newton_ranks}
    leg_pos = {r.user_id: r.rank for r in legacy_ranks}
    ids = sorted(set(new_pos) | set(leg_pos))
    rows = []
    for uid in ids:
        n = new_pos.get(uid)
        o = leg_pos.get(uid)
        rows.append(
            {
                "user_id": uid,
                "newton_rank": n,
                "legacy_rank": o,
                "delta_newton_minus_legacy": (n - o) if n is not None and o is not None else None,
            }
        )
    return rows
