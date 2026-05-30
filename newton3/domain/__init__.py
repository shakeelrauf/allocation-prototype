"""Domain logic: scoring, allocation, events, fairness (hackathon core)."""

from newton3.domain.models import (
    AllocationResult,
    BehaviorEvent,
    EventType,
    Tier,
    UserProfile,
    UserScoreState,
    tier_for_score,
    utcnow,
)

__all__ = [
    "AllocationResult",
    "BehaviorEvent",
    "EventType",
    "Tier",
    "UserProfile",
    "UserScoreState",
    "tier_for_score",
    "utcnow",
]
