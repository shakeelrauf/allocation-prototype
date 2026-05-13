"""Route inbound events to scoring updates."""

from __future__ import annotations

from dataclasses import dataclass

from models import BehaviorEvent, EventType, UserProfile, tier_for_score, utcnow
from observability import emit
from scoring_engine import apply_carpool_reward, apply_penalty, apply_weekly_decay
from store import ScoreStore
from tenant_weights import resolve_weights


@dataclass
class ProcessResult:
    user_id: str
    event_type: str
    applied: bool
    detail: str
    score_after: float


def _norm_type(t: EventType | str) -> str:
    if isinstance(t, EventType):
        return t.value
    return str(t)


def _snapshot(
    store: ScoreStore,
    uid: str,
    score: float,
    et: str,
    detail: str,
    applied: bool,
) -> None:
    fn = getattr(store, "record_score_history", None)
    if callable(fn):
        fn(uid, score, tier_for_score(score).value, et, detail, applied)


def process_event(store: ScoreStore, event: BehaviorEvent) -> ProcessResult:
    """Apply score changes for known event types; log all."""
    store.log_event(event)
    uid = event.user_id
    et = _norm_type(event.event_type)
    state = store.get_score_state(uid)
    w = resolve_weights(store, uid)

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
        _snapshot(store, uid, state.score, et, "no score change", False)
        return ProcessResult(uid, et, False, "no score change", state.score)

    if et == EventType.UNUSED_BOOKING.value:
        r = apply_penalty(state, w.no_show, "unused_booking", event.timestamp)
        store.save_score_state(state)
        detail = "; ".join(r.notes)
        emit("newton3.event", user_id=uid, event_type=et, applied=True, score=state.score, detail=detail)
        _snapshot(store, uid, state.score, et, detail, True)
        return ProcessResult(uid, et, True, detail, state.score)

    if et == EventType.FREE_SPACE_USED.value:
        r = apply_penalty(state, w.free_space, "free_space_used", event.timestamp)
        store.save_score_state(state)
        detail = "; ".join(r.notes)
        emit("newton3.event", user_id=uid, event_type=et, applied=True, score=state.score, detail=detail)
        _snapshot(store, uid, state.score, et, detail, True)
        return ProcessResult(uid, et, True, detail, state.score)

    if et in (EventType.OFFENCE_REPORTED.value, "offence"):
        r = apply_penalty(state, w.offence, "offence", event.timestamp)
        store.save_score_state(state)
        detail = "; ".join(r.notes)
        emit("newton3.event", user_id=uid, event_type=et, applied=True, score=state.score, detail=detail)
        _snapshot(store, uid, state.score, et, detail, True)
        return ProcessResult(uid, et, True, detail, state.score)

    if et in (EventType.CARPOOL_DETECTED.value, "carpool"):
        r = apply_carpool_reward(state, event.timestamp, weights=w)
        store.save_score_state(state)
        detail = "; ".join(r.notes)
        emit("newton3.event", user_id=uid, event_type=et, applied=True, score=state.score, detail=detail)
        _snapshot(store, uid, state.score, et, detail, True)
        return ProcessResult(uid, et, True, detail, state.score)

    if et == EventType.WEEKLY_DECAY.value:
        weeks = int(event.payload.get("weeks", 1))
        r = apply_weekly_decay(state, weeks=weeks, at=event.timestamp, weights=w)
        store.save_score_state(state)
        detail = "; ".join(r.notes)
        emit("newton3.event", user_id=uid, event_type=et, applied=True, score=state.score, detail=detail)
        _snapshot(store, uid, state.score, et, detail, True)
        return ProcessResult(uid, et, True, detail, state.score)

    state.updated_at = event.timestamp or utcnow()
    store.save_score_state(state)
    detail = f"unknown event type: {et}"
    emit("newton3.event", user_id=uid, event_type=et, applied=False, score=state.score, detail=detail)
    _snapshot(store, uid, state.score, et, detail, False)
    return ProcessResult(uid, et, False, detail, state.score)


def seed_users(store: ScoreStore, profiles: list[UserProfile]) -> None:
    for p in profiles:
        store.ensure_user(p)
