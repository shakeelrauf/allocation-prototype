"""Behaviour score calculation: penalties, rewards (capped), decay toward base."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from models import Tier, UserScoreState, tier_for_score, utcnow
from tenant_weights import TenantWeights

BASE_SCORE = 100.0
MIN_SCORE = 0.0
REWARD_CAP_WINDOW_DAYS = 28
REWARD_CAP_TOTAL = 20.0
DECAY_PER_WEEK = 2.0

NO_SHOW_POINTS = 3.0
FREE_SPACE_POINTS = 1.0
OFFENCE_POINTS = 5.0
CARPOOL_POINTS = 5.0


def _tw(weights: TenantWeights | None) -> TenantWeights:
    return weights if weights is not None else TenantWeights.default()


@dataclass
class ScoreAdjustResult:
    score_before: float
    score_after: float
    delta: float
    tier_before: Tier
    tier_after: Tier
    notes: list[str]


def _trim_reward_history(state: UserScoreState, end: datetime, window_days: int) -> None:
    cutoff = end - timedelta(days=window_days)
    state.reward_grants = [(ts, p) for ts, p in state.reward_grants if ts >= cutoff]


def reward_headroom(
    state: UserScoreState,
    at: datetime | None = None,
    weights: TenantWeights | None = None,
) -> float:
    """Remaining carpool/reward capacity in the rolling window (tenant-configurable)."""
    w = _tw(weights)
    now = at or utcnow()
    _trim_reward_history(state, now, w.reward_cap_window_days)
    used = state.rolling_reward_total(w.reward_cap_window_days, now)
    return max(0.0, w.reward_cap_total - used)


def decay_headroom_to_base(state: UserScoreState) -> float:
    """Points we may add via decay without pushing above BASE_SCORE."""
    return max(0.0, BASE_SCORE - state.score)


def apply_weekly_decay(
    state: UserScoreState,
    weeks: int = 1,
    at: datetime | None = None,
    weights: TenantWeights | None = None,
) -> ScoreAdjustResult:
    """
    Scheduler-driven recovery: +2 per elapsed week toward BASE_SCORE, capped.
    Spec: decay = min(weeks * 2, base_score - current_score) when current <= base.
    """
    w = _tw(weights)
    now = at or utcnow()
    before = state.score
    tier_b = tier_for_score(before)
    if weeks < 1:
        weeks = 1
    raw = w.decay_per_week * weeks
    delta = min(raw, decay_headroom_to_base(state))
    state.score = max(MIN_SCORE, state.score + delta)
    state.last_decay_at = now
    state.updated_at = now
    tid = tier_for_score(state.score)
    headroom = max(0.0, BASE_SCORE - before)
    notes = [
        f"weekly_decay: +{delta:g} (weeks={weeks}, raw={raw:g}, headroom_to_base={headroom:.2f})"
    ]
    return ScoreAdjustResult(before, state.score, delta, tier_b, tid, notes)


def apply_penalty(
    state: UserScoreState,
    points: float,
    reason: str,
    at: datetime | None = None,
) -> ScoreAdjustResult:
    now = at or utcnow()
    before = state.score
    tier_b = tier_for_score(before)
    delta = -abs(points)
    state.score = max(MIN_SCORE, state.score + delta)
    state.last_penalty_at = now
    state.updated_at = now
    tid = tier_for_score(state.score)
    notes = [f"{reason}: {delta:g}"]
    return ScoreAdjustResult(before, state.score, delta, tier_b, tid, notes)


def apply_carpool_reward(
    state: UserScoreState,
    at: datetime | None = None,
    weights: TenantWeights | None = None,
) -> ScoreAdjustResult:
    w = _tw(weights)
    now = at or utcnow()
    _trim_reward_history(state, now, w.reward_cap_window_days)
    before = state.score
    tier_b = tier_for_score(before)
    head = reward_headroom(state, now, weights=w)
    grant = min(w.carpool, head)
    if grant <= 0:
        state.updated_at = now
        return ScoreAdjustResult(
            before,
            state.score,
            0.0,
            tier_b,
            tier_for_score(state.score),
            ["carpool: skipped (rolling reward cap reached)"],
        )
    state.score = max(MIN_SCORE, state.score + grant)
    state.reward_grants.append((now, grant))
    state.updated_at = now
    tid = tier_for_score(state.score)
    notes = [f"carpool: +{grant:g} (headroom was {head:g})"]
    return ScoreAdjustResult(before, state.score, grant, tier_b, tid, notes)


def reset_cycle(state: UserScoreState, at: datetime | None = None) -> None:
    """Optional: reset/rerun after a major allocation cycle (MVP hook)."""
    now = at or utcnow()
    state.score = BASE_SCORE
    state.last_penalty_at = None
    state.last_decay_at = None
    state.reward_grants.clear()
    state.updated_at = now
