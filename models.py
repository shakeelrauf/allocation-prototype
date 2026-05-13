"""Domain models for Newton 3.0 scoring and allocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    BOOKING_CREATED = "booking.created"
    BOOKING_CANCELLED = "booking.cancelled"
    BOOKING_COMPLETED = "booking.completed"
    GATE_ENTRY_DETECTED = "gate.entry_detected"
    OFFENCE_REPORTED = "offence.reported"
    CARPOOL_DETECTED = "carpool.detected"
    UNUSED_BOOKING = "unused_booking"
    FREE_SPACE_USED = "free_space_used"
    WEEKLY_DECAY = "weekly_decay"


@dataclass
class BehaviorEvent:
    """Inbound scoring/allocation-related event."""

    event_type: EventType | str
    user_id: str
    timestamp: datetime | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = utcnow()
        if isinstance(self.event_type, str):
            try:
                self.event_type = EventType(self.event_type)
            except ValueError:
                pass


@dataclass
class UserProfile:
    """Static-ish allocation inputs (admin-controlled)."""

    user_id: str
    group_id: str
    group_priority: int = 100
    user_priority: int = 100


@dataclass
class UserScoreState:
    """Mutable behaviour score state for one user."""

    user_id: str
    score: float = 100.0
    last_penalty_at: datetime | None = None
    last_decay_at: datetime | None = None
    updated_at: datetime = field(default_factory=utcnow)
    reward_grants: list[tuple[datetime, float]] = field(default_factory=list)

    def rolling_reward_total(self, window_days: int, end: datetime) -> float:
        from datetime import timedelta

        cutoff = end - timedelta(days=window_days)
        return sum(p for ts, p in self.reward_grants if ts >= cutoff)


class Tier(str, Enum):
    PLATINUM = "Platinum"
    GOLD = "Gold"
    SILVER = "Silver"
    BRONZE = "Bronze"
    RESTRICTED = "Restricted"


def tier_for_score(score: float) -> Tier:
    if score >= 150:
        return Tier.PLATINUM
    if score >= 120:
        return Tier.GOLD
    if score >= 80:
        return Tier.SILVER
    if score >= 50:
        return Tier.BRONZE
    return Tier.RESTRICTED


@dataclass
class AllocationResult:
    """Rank output with optional explanation."""

    user_id: str
    rank: int
    sort_key: tuple[Any, ...]
    explain: str
