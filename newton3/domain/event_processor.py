"""Route inbound events to scoring updates."""

from __future__ import annotations

from dataclasses import dataclass

from newton3.domain.models import BehaviorEvent, EventType, UserProfile, tier_for_score, utcnow
from newton3.observability import emit
from newton3.domain.scoring_engine import ScoreAdjustResult, apply_carpool_reward, apply_penalty, apply_weekly_decay
from newton3.persistence.store import ScoreStore
from newton3.domain.tenant_weights import resolve_weights


@dataclass
class ProcessResult:
    user_id: str
    event_type: str
    applied: bool
    detail: str
    score_after: float
    score_before: float = 0.0
    score_delta: float = 0.0
    tier_before: str = ""
    tier_after: str = ""


def _norm_type(t: EventType | str) -> str:
    if isinstance(t, EventType):
        return t.value
    return str(t)


def _make_result(
    uid: str,
    et: str,
    applied: bool,
    detail: str,
    before: float,
    after: float,
    tier_b,
    tier_a,
) -> ProcessResult:
    return ProcessResult(
        uid,
        et,
        applied,
        detail,
        after,
        score_before=before,
        score_delta=after - before,
        tier_before=tier_b.value if hasattr(tier_b, "value") else str(tier_b),
        tier_after=tier_a.value if hasattr(tier_a, "value") else str(tier_a),
    )


def _from_adjust(uid: str, et: str, applied: bool, adj: ScoreAdjustResult) -> ProcessResult:
    return ProcessResult(
        uid,
        et,
        applied,
        "; ".join(adj.notes),
        adj.score_after,
        score_before=adj.score_before,
        score_delta=adj.delta,
        tier_before=adj.tier_before.value,
        tier_after=adj.tier_after.value,
    )


def _snapshot(
    store: ScoreStore,
    uid: str,
    score: float,
    et: str,
    detail: str,
    applied: bool,
    *,
    score_before: float | None = None,
) -> None:
    fn = getattr(store, "record_score_history", None)
    if callable(fn):
        fn(
            uid,
            score,
            tier_for_score(score).value,
            et,
            detail,
            applied,
            score_before=score_before,
        )


def process_event(store: ScoreStore, event: BehaviorEvent) -> ProcessResult:
    """Apply score changes for known event types; log all."""
    store.log_event(event)
    uid = event.user_id
    et = _norm_type(event.event_type)
    state = store.get_score_state(uid)
    w = resolve_weights(store, uid)
    before = state.score
    tier_b = tier_for_score(before)

    # Passive events
    if et in (
        EventType.BOOKING_CREATED.value,
        EventType.BOOKING_CANCELLED.value,
        EventType.BOOKING_COMPLETED.value,
        EventType.GATE_ENTRY_DETECTED.value,
    ):
        state.updated_at = event.timestamp or utcnow()
        store.save_score_state(state)
        emit("newton3.event", user_id=uid, event_type=et, applied=False, score=state.score)
        _snapshot(store, uid, state.score, et, "no score change", False, score_before=before)
        return _make_result(uid, et, False, "no score change", before, state.score, tier_b, tier_for_score(state.score))

    if et == EventType.UNUSED_BOOKING.value:
        r = apply_penalty(state, w.no_show, "unused_booking", event.timestamp)
        store.save_score_state(state)
        detail = "; ".join(r.notes)
        emit("newton3.event", user_id=uid, event_type=et, applied=True, score=state.score, detail=detail)
        _snapshot(store, uid, state.score, et, detail, True, score_before=r.score_before)
        return _from_adjust(uid, et, True, r)

    if et == EventType.FREE_SPACE_USED.value:
        r = apply_penalty(state, w.free_space, "free_space_used", event.timestamp)
        store.save_score_state(state)
        detail = "; ".join(r.notes)
        emit("newton3.event", user_id=uid, event_type=et, applied=True, score=state.score, detail=detail)
        _snapshot(store, uid, state.score, et, detail, True, score_before=r.score_before)
        return _from_adjust(uid, et, True, r)

    if et in (EventType.OFFENCE_REPORTED.value, "offence"):
        r = apply_penalty(state, w.offence, "offence", event.timestamp)
        store.save_score_state(state)
        detail = "; ".join(r.notes)
        emit("newton3.event", user_id=uid, event_type=et, applied=True, score=state.score, detail=detail)
        _snapshot(store, uid, state.score, et, detail, True, score_before=r.score_before)
        return _from_adjust(uid, et, True, r)

    if et in (EventType.CARPOOL_DETECTED.value, "carpool"):
        r = apply_carpool_reward(state, event.timestamp, weights=w)
        store.save_score_state(state)
        detail = "; ".join(r.notes)
        emit("newton3.event", user_id=uid, event_type=et, applied=True, score=state.score, detail=detail)
        _snapshot(store, uid, state.score, et, detail, True, score_before=r.score_before)
        return _from_adjust(uid, et, True, r)

    if et == EventType.WEEKLY_DECAY.value:
        weeks = int(event.payload.get("weeks", 1))
        r = apply_weekly_decay(state, weeks=weeks, at=event.timestamp, weights=w)
        store.save_score_state(state)
        detail = "; ".join(r.notes)
        emit("newton3.event", user_id=uid, event_type=et, applied=True, score=state.score, detail=detail)
        _snapshot(store, uid, state.score, et, detail, True, score_before=r.score_before)
        return _from_adjust(uid, et, True, r)

    state.updated_at = event.timestamp or utcnow()
    store.save_score_state(state)
    detail = f"unknown event type: {et}"
    emit("newton3.event", user_id=uid, event_type=et, applied=False, score=state.score, detail=detail)
    _snapshot(store, uid, state.score, et, detail, False, score_before=before)
    return _make_result(uid, et, False, detail, before, state.score, tier_b, tier_for_score(state.score))


def seed_users(store: ScoreStore, profiles: list[UserProfile]) -> None:
    for p in profiles:
        store.ensure_user(p)
