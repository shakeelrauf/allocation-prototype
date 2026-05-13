"""Heuristic insights: population anomaly + no-show risk (prototype ML hooks)."""

from __future__ import annotations

import statistics
from typing import Any

from models import EventType, tier_for_score
from store import ScoreStore


def score_anomaly(store: ScoreStore, user_id: str) -> dict[str, Any]:
    """Z-score vs registered users (simple 'ML-ready' baseline)."""
    profiles = store.list_profiles()
    scores = [store.get_score_state(p.user_id).score for p in profiles]
    mine = store.get_score_state(user_id).score
    if len(scores) < 3:
        return {
            "user_id": user_id,
            "z_score": None,
            "population_mean": statistics.mean(scores) if scores else None,
            "flag_outlier": False,
            "note": "need ≥3 users for z-score",
        }
    mean = statistics.mean(scores)
    stdev = statistics.pstdev(scores)
    denom = stdev if stdev > 1e-9 else 1.0
    z = (mine - mean) / denom
    return {
        "user_id": user_id,
        "score": mine,
        "tier": tier_for_score(mine).value,
        "population_mean": mean,
        "population_stdev": stdev,
        "z_score": z,
        "flag_outlier": abs(z) >= 2.0,
    }


def no_show_risk(store: ScoreStore, user_id: str, *, event_lookback: int = 300) -> dict[str, Any]:
    """Heuristic risk from recent unused_booking density (predictive allocation stub)."""
    events = store.recent_events(event_lookback)
    unused = 0
    carpool = 0
    for ev in events:
        et = ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type)
        if ev.user_id != user_id:
            continue
        if et == EventType.UNUSED_BOOKING.value:
            unused += 1
        if et in (EventType.CARPOOL_DETECTED.value, "carpool"):
            carpool += 1

    raw = 0.12 * unused - 0.04 * min(carpool, 5)
    risk = max(0.0, min(1.0, 0.15 + raw))
    return {
        "user_id": user_id,
        "unused_booking_events_seen": unused,
        "carpool_events_seen": carpool,
        "estimated_no_show_risk_0_1": round(risk, 3),
        "model": "heuristic_v1",
    }


def ensemble_anomaly_flags(store: ScoreStore, user_id: str) -> dict[str, Any]:
    """Placeholder for multi-signal anomaly detection (combine z-score + event spikes)."""
    z = score_anomaly(store, user_id)
    ns = no_show_risk(store, user_id)
    spike = ns["unused_booking_events_seen"] >= 3
    return {
        "user_id": user_id,
        "z_score": z.get("z_score"),
        "z_flag": z.get("flag_outlier"),
        "no_show_risk": ns.get("estimated_no_show_risk_0_1"),
        "burst_unused_bookings": spike,
        "ensemble_flag": bool(z.get("flag_outlier")) or spike,
        "note": "Replace with isolation forest / seasonal model for production",
    }
