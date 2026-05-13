"""Rank users for allocation: group → user override → behaviour → tie-break.

Users in **Restricted** tier (behaviour score below Bronze) are ranked **after** all
eligible users using the same key among themselves, so ``allocate_spaces`` never awards
a slot to a Restricted driver when any non-Restricted competitor is in the pool.
"""

from __future__ import annotations

import random
from typing import Any, Sequence

from models import AllocationResult, Tier, UserProfile, tier_for_score
from store import ScoreStore


def allocation_sort_key(
    profile: UserProfile,
    behavior_score: float,
    tie_breaker: float | None = None,
) -> tuple[int, int, float, float]:
    tb = random.random() if tie_breaker is None else tie_breaker
    return (
        profile.group_priority,
        profile.user_priority,
        -behavior_score,
        tb,
    )


def rank_users(
    store: ScoreStore,
    user_ids: Sequence[str],
    *,
    seed: int | None = None,
) -> list[AllocationResult]:
    """
    Sort key is ``(group_priority, user_priority, -behavior_score, tie_breaker)`` ascending:
    lower ``group_priority`` first, then lower ``user_priority``, then higher behaviour score,
    then lower ``tie_breaker`` (uniform in [0,1), fixed when ``seed`` is set).

    **Restricted** tier (score in Restricted band) is sorted after every eligible user so
    parking slots are not given to Restricted drivers while eligible alternatives exist.
    """
    if seed is not None:
        random.seed(seed)

    candidates: list[tuple[UserProfile, float, float]] = []
    for uid in user_ids:
        prof = store.get_profile(uid)
        if prof is None:
            continue
        score = store.get_score_state(uid).score
        tb = random.random()
        candidates.append((prof, score, tb))

    def row_sort_key(row: tuple[UserProfile, float, float]) -> tuple[int, int, float, float]:
        return allocation_sort_key(row[0], row[1], row[2])

    eligible = [c for c in candidates if tier_for_score(c[1]) != Tier.RESTRICTED]
    ineligible = [c for c in candidates if tier_for_score(c[1]) == Tier.RESTRICTED]
    eligible.sort(key=row_sort_key)
    ineligible.sort(key=row_sort_key)
    ordered = eligible + ineligible

    out: list[AllocationResult] = []
    for rank, (prof, score, tb) in enumerate(ordered, start=1):
        sk = allocation_sort_key(prof, score, tb)
        tier = tier_for_score(score)
        explain = (
            f"rank={rank}: group_priority={prof.group_priority}, "
            f"user_priority={prof.user_priority}, behavior_score={score:.2f}, "
            f"tier={tier.value}, tie_breaker={tb:.4f}"
        )
        if tier == Tier.RESTRICTED:
            explain += " | not eligible for space while other tiers are in pool"
        out.append(
            AllocationResult(
                user_id=prof.user_id,
                rank=rank,
                sort_key=sk,
                explain=explain,
            )
        )
    return out


def allocate_spaces(
    store: ScoreStore,
    user_ids: Sequence[str],
    capacity: int,
    *,
    seed: int | None = None,
) -> list[AllocationResult]:
    ranked = rank_users(store, user_ids, seed=seed)
    return ranked[: max(0, capacity)]


def allocation_explain_for_user(
    store: ScoreStore,
    user_ids: Sequence[str],
    focus_user_id: str,
    *,
    seed: int | None = None,
) -> dict[str, Any]:
    """Human-oriented explanation of why one user sits at their rank."""
    ranked = rank_users(store, user_ids, seed=seed)
    by_user = {r.user_id: r for r in ranked}
    focus = by_user.get(focus_user_id)
    if focus is None:
        return {
            "error": "user not in pool or not registered",
            "focus_user_id": focus_user_id,
        }
    ahead = [r for r in ranked if r.rank < focus.rank]
    narrative = [
        f"{focus.user_id} is rank {focus.rank} of {len(ranked)} in this run.",
        "Anyone ranked above them wins an earlier slot under Newton 3 rules:",
    ]
    for r in ahead:
        narrative.append(f"  #{r.rank} {r.user_id} — {r.explain}")
    if not ahead:
        narrative.append("  (nobody — top of this pool for this seed.)")
    return {
        "focus_user_id": focus_user_id,
        "rank": focus.rank,
        "explain": focus.explain,
        "users_above": [
            {"rank": r.rank, "user_id": r.user_id, "explain": r.explain} for r in ahead
        ],
        "narrative": "\n".join(narrative),
        "ranking": [
            {"rank": r.rank, "user_id": r.user_id, "explain": r.explain} for r in ranked
        ],
    }
