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


def _why_user_ranks_above(
    above_meta: dict[str, Any],
    focus_meta: dict[str, Any],
) -> str:
    """Plain-language reason *above* beats *focus* in the sorted pool."""
    o_prof = above_meta["profile"]
    f_prof = focus_meta["profile"]
    o_score = above_meta["behavior_score"]
    f_score = focus_meta["behavior_score"]
    o_tier: Tier = above_meta["tier"]
    f_tier: Tier = focus_meta["tier"]
    o_tb = above_meta["tie_breaker"]
    f_tb = focus_meta["tie_breaker"]

    if f_tier == Tier.RESTRICTED and o_tier != Tier.RESTRICTED:
        return (
            f"They are {o_tier.value} (score {o_score:.2f}); you are Restricted "
            f"(score {f_score:.2f}). Eligible tiers are always ranked before Restricted."
        )
    if o_prof.group_priority < f_prof.group_priority:
        return (
            f"Team priority {o_prof.group_priority} beats yours ({f_prof.group_priority}) — "
            "lower team priority number wins."
        )
    if o_prof.group_priority > f_prof.group_priority:
        return (
            f"Same behaviour rules but they sort earlier in the Restricted-only sub-list "
            f"(team priority {o_prof.group_priority} vs yours {f_prof.group_priority})."
        )
    if o_prof.user_priority < f_prof.user_priority:
        return (
            f"Same team priority ({o_prof.group_priority}); their individual priority "
            f"{o_prof.user_priority} beats yours ({f_prof.user_priority})."
        )
    if o_prof.user_priority > f_prof.user_priority:
        return (
            f"Same team priority; they rank higher within the same tier band by individual "
            f"priority ({o_prof.user_priority} vs {f_prof.user_priority})."
        )
    if o_score > f_score:
        return (
            f"Same team & individual priority; behaviour score {o_score:.2f} beats "
            f"yours ({f_score:.2f})."
        )
    if o_score < f_score:
        return (
            f"Same priorities; your score is higher but they still rank above due to "
            "Restricted / pool ordering for this seed."
        )
    if o_tb < f_tb:
        return (
            f"Identical priorities and score — tie-breaker {o_tb:.6f} vs yours {f_tb:.6f} "
            "(lower wins; fixed by seed)."
        )
    return (
        f"Tie-breaker {o_tb:.6f} vs yours {f_tb:.6f} — they sort earlier at equal score "
        "and priorities."
    )


def _build_ranked_pool(
    store: ScoreStore,
    user_ids: Sequence[str],
    *,
    seed: int | None = None,
) -> tuple[list[AllocationResult], dict[str, dict[str, Any]], int]:
    """
    Returns (ranked results, per-user meta, eligible_count).
    Meta holds profile, score, tier, tie_breaker, sort_key, restricted_deferred.
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
    eligible_count = len(eligible)

    meta_by_user: dict[str, dict[str, Any]] = {}
    out: list[AllocationResult] = []
    for rank, (prof, score, tb) in enumerate(ordered, start=1):
        sk = allocation_sort_key(prof, score, tb)
        tier = tier_for_score(score)
        restricted_deferred = tier == Tier.RESTRICTED and eligible_count > 0
        meta_by_user[prof.user_id] = {
            "profile": prof,
            "behavior_score": score,
            "tier": tier,
            "tie_breaker": tb,
            "sort_key": sk,
            "restricted_deferred": restricted_deferred,
        }
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
    return out, meta_by_user, eligible_count


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
    ranked, _, _ = _build_ranked_pool(store, user_ids, seed=seed)
    return ranked


def _focus_calculation_steps(
    focus_meta: dict[str, Any],
    *,
    rank: int,
    pool_size: int,
    seed: int | None,
    eligible_count: int,
) -> list[dict[str, Any]]:
    prof: UserProfile = focus_meta["profile"]
    score = focus_meta["behavior_score"]
    tier: Tier = focus_meta["tier"]
    tb = focus_meta["tie_breaker"]
    sk = focus_meta["sort_key"]
    steps: list[dict[str, Any]] = [
        {
            "step": 1,
            "title": "Ranking pool",
            "value": f"{pool_size} drivers",
            "detail": (
                f"Seed {seed} fixes tie-breaker draws. "
                "Everyone in the Parking pool is sorted into one list."
                if seed is not None
                else "No seed — tie-breakers change each run."
            ),
        },
        {
            "step": 2,
            "title": "Team priority (group)",
            "value": str(prof.group_priority),
            "detail": (
                f"Group «{prof.group_id}». Lower number = earlier in line. "
                f"Your sort-key component: {sk[0]}."
            ),
        },
        {
            "step": 3,
            "title": "Individual priority",
            "value": str(prof.user_priority),
            "detail": (
                f"Admin override within the team. Lower wins. Sort-key component: {sk[1]}."
            ),
        },
        {
            "step": 4,
            "title": "Behaviour score → tier",
            "value": f"{score:.2f} ({tier.value})",
            "detail": (
                "Tiers: Platinum ≥150, Gold ≥120, Silver ≥80, Bronze ≥50, else Restricted. "
                f"Sort uses −score so key component = {sk[2]:.2f} (higher real score → smaller −score)."
            ),
        },
        {
            "step": 5,
            "title": "Tie-breaker",
            "value": f"{tb:.6f}",
            "detail": (
                "Random in [0, 1); lower wins when priorities and score tie. "
                f"Sort-key component: {sk[3]:.6f}."
            ),
        },
        {
            "step": 6,
            "title": "Full sort key (ascending wins)",
            "value": f"({sk[0]}, {sk[1]}, {sk[2]:.2f}, {sk[3]:.6f})",
            "detail": (
                "(team priority, individual priority, −behaviour score, tie-breaker) — "
                "Python compares left to right; smaller tuple sorts earlier."
            ),
        },
    ]
    if focus_meta["restricted_deferred"]:
        steps.append(
            {
                "step": 7,
                "title": "Restricted placement",
                "value": f"After {eligible_count} eligible drivers",
                "detail": (
                    "Restricted tier cannot take a space ahead of any eligible driver "
                    "while alternatives exist in the pool."
                ),
            }
        )
    steps.append(
        {
            "step": len(steps) + 1,
            "title": "Final rank",
            "value": f"#{rank} of {pool_size}",
            "detail": (
                f"{rank - 1} driver(s) sort earlier under these rules"
                if rank > 1
                else "Top of the pool for this seed."
            ),
        }
    )
    return steps


def _meta_to_public(meta: dict[str, Any]) -> dict[str, Any]:
    prof: UserProfile = meta["profile"]
    sk = meta["sort_key"]
    tier: Tier = meta["tier"]
    return {
        "group_id": prof.group_id,
        "group_priority": prof.group_priority,
        "user_priority": prof.user_priority,
        "behavior_score": round(meta["behavior_score"], 2),
        "tier": tier.value,
        "tie_breaker": round(meta["tie_breaker"], 6),
        "sort_key": {
            "group_priority": sk[0],
            "user_priority": sk[1],
            "neg_behavior_score": round(sk[2], 2),
            "tie_breaker": round(sk[3], 6),
        },
        "restricted_deferred": meta["restricted_deferred"],
    }


def allocate_spaces(
    store: ScoreStore,
    user_ids: Sequence[str],
    capacity: int,
    *,
    seed: int | None = None,
) -> list[AllocationResult]:
    ranked = rank_users(store, user_ids, seed=seed)
    return ranked[: max(0, capacity)]


def human_allocation_line(
    profile: UserProfile,
    behavior_score: float,
    rank: int,
    *,
    capacity: int,
    pool_size: int,
    got_space: bool,
) -> str:
    """Plain-language line for UI: who got parking and why."""
    tier = tier_for_score(behavior_score)
    if got_space:
        slot = f"Parking space #{rank}" if capacity > 1 else "The parking space"
        spaces = f"{capacity} space{'s' if capacity != 1 else ''}"
        return (
            f"{slot} is yours. You were #{rank} in line out of {pool_size} drivers "
            f"({spaces} available). Behaviour: {behavior_score:.0f} ({tier.value})."
        )
    if tier == Tier.RESTRICTED:
        return (
            f"No parking this run — behaviour is Restricted ({behavior_score:.0f}). "
            f"Drivers with stronger scores were given the {capacity} available space"
            f"{'' if capacity == 1 else 's'} first."
        )
    if rank <= capacity + 5:
        spaces = f"{capacity} space{'s' if capacity != 1 else ''}"
        return (
            f"No parking this run — you were #{rank} in line, but only {spaces} "
            f"were available. You are next if another space opens."
        )
    return (
        f"No parking this run — position #{rank} of {pool_size}. "
        f"Behaviour {behavior_score:.0f} ({tier.value})."
    )


def build_allocation_outcome(
    store: ScoreStore,
    user_ids: Sequence[str],
    capacity: int,
    *,
    seed: int | None = None,
    waitlist_limit: int = 15,
) -> dict[str, Any]:
    """Full ranked pool split into assigned spaces vs waitlist with human summaries."""
    cap = max(0, capacity)
    ranked = rank_users(store, user_ids, seed=seed)
    pool_size = len(ranked)

    def row_dict(r: AllocationResult, got_space: bool) -> dict[str, Any]:
        prof = store.get_profile(r.user_id)
        score = store.get_score_state(r.user_id).score
        return {
            "rank": r.rank,
            "user_id": r.user_id,
            "got_parking": got_space,
            "parking_slot": r.rank if got_space else None,
            "behavior_score": round(score, 2),
            "tier": tier_for_score(score).value,
            "group_priority": prof.group_priority if prof else None,
            "user_priority": prof.user_priority if prof else None,
            "explain": r.explain,
            "summary": human_allocation_line(
                prof,
                score,
                r.rank,
                capacity=cap,
                pool_size=pool_size,
                got_space=got_space,
            )
            if prof
            else r.explain,
        }

    assigned = [row_dict(r, True) for r in ranked[:cap]]
    waiting = [row_dict(r, False) for r in ranked[cap : cap + waitlist_limit]]
    return {
        "pool_size": pool_size,
        "capacity": cap,
        "assigned": assigned,
        "waiting": waiting,
        "waiting_total": max(0, pool_size - cap),
    }


def allocation_explain_for_user(
    store: ScoreStore,
    user_ids: Sequence[str],
    focus_user_id: str,
    *,
    seed: int | None = None,
) -> dict[str, Any]:
    """Human-oriented explanation of why one user sits at their rank."""
    ranked, meta_by_user, eligible_count = _build_ranked_pool(store, user_ids, seed=seed)
    by_user = {r.user_id: r for r in ranked}
    focus = by_user.get(focus_user_id)
    if focus is None:
        return {
            "error": "user not in pool or not registered",
            "focus_user_id": focus_user_id,
        }
    focus_meta = meta_by_user[focus_user_id]
    pool_size = len(ranked)
    ahead = [r for r in ranked if r.rank < focus.rank]
    focus_public = _meta_to_public(focus_meta)
    focus_public["user_id"] = focus_user_id
    focus_public["rank"] = focus.rank
    focus_public["pool_size"] = pool_size
    focus_public["seed"] = seed
    focus_public["eligible_count"] = eligible_count
    focus_public["calculation_steps"] = _focus_calculation_steps(
        focus_meta,
        rank=focus.rank,
        pool_size=pool_size,
        seed=seed,
        eligible_count=eligible_count,
    )
    focus_public["sort_formula"] = (
        "rank = position in list sorted by "
        "(team_priority ↑, user_priority ↑, behaviour_score ↓, tie_breaker ↑), "
        "with all Restricted drivers after every eligible driver."
    )

    why_above: list[dict[str, Any]] = []
    for r in ahead:
        other_meta = meta_by_user[r.user_id]
        why_above.append(
            {
                "rank": r.rank,
                "user_id": r.user_id,
                "explain": r.explain,
                "reason": _why_user_ranks_above(other_meta, focus_meta),
                "their": _meta_to_public(other_meta),
            }
        )

    narrative = [
        f"{focus.user_id} is rank {focus.rank} of {pool_size} in this run.",
        "",
        "Your numbers:",
        f"  Team «{focus_public['group_id']}» priority {focus_public['group_priority']}",
        f"  Individual priority {focus_public['user_priority']}",
        f"  Behaviour score {focus_public['behavior_score']:.2f} ({focus_public['tier']})",
        f"  Tie-breaker {focus_public['tie_breaker']:.6f}",
        f"  Sort key {focus_public['sort_key']}",
        "",
        "Anyone ranked above you:",
    ]
    for row in why_above:
        narrative.append(f"  #{row['rank']} {row['user_id']} — {row['reason']}")
    if not why_above:
        narrative.append("  (nobody — top of this pool for this seed.)")

    return {
        "focus_user_id": focus_user_id,
        "rank": focus.rank,
        "explain": focus.explain,
        "focus_detail": focus_public,
        "users_above": why_above,
        "why_above": why_above,
        "narrative": "\n".join(narrative),
        "ranking": [
            {"rank": r.rank, "user_id": r.user_id, "explain": r.explain} for r in ranked
        ],
    }
