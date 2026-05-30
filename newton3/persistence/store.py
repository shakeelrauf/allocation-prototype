"""Persistence abstraction: in-memory for tests; SQLite for local demos."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Protocol, runtime_checkable

from newton3.domain.models import AllocationResult, BehaviorEvent, UserProfile, UserScoreState, tier_for_score, utcnow


def _attach_score_deltas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest-first rows; attach score_delta from score_before or previous snapshot."""
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        r = dict(row)
        score = float(r["score"])
        sb = r.get("score_before")
        if sb is not None:
            delta = score - float(sb)
        elif i + 1 < len(rows):
            delta = score - float(rows[i + 1]["score"])
        else:
            delta = 0.0
        r["score_delta"] = round(delta, 2)
        if sb is not None:
            r["score_before"] = float(sb)
        out.append(r)
    return out


@runtime_checkable
class ScoreStore(Protocol):
    """Minimal surface used by scoring, allocation, and API layers."""

    def ensure_user(self, profile: UserProfile) -> None: ...

    def get_profile(self, user_id: str) -> UserProfile | None: ...

    def get_score_state(self, user_id: str) -> UserScoreState: ...

    def save_score_state(self, state: UserScoreState) -> None: ...

    def log_event(self, event: BehaviorEvent) -> None: ...

    def recent_events(self, limit: int = 50, *, user_id: str | None = None) -> list[BehaviorEvent]: ...

    def list_profiles(self) -> list[UserProfile]: ...

    def record_space_allocation(
        self,
        pool_user_ids: list[str],
        capacity: int,
        seed: int | None,
        winners: list[AllocationResult],
    ) -> int:
        """Persist one allocation decision; returns run id."""
        ...

    def list_space_allocations(self, limit: int = 50) -> list[dict[str, Any]]:
        """Newest first; each dict has id, created_at, seed, capacity, pool_user_ids, winners."""
        ...

    def get_space_allocation(self, run_id: int) -> dict[str, Any] | None:
        """Single run in the same shape as list items, or None."""
        ...


class InMemoryStore:
    def __init__(self) -> None:
        self._profiles: dict[str, UserProfile] = {}
        self._scores: dict[str, UserScoreState] = {}
        self._event_log: list[BehaviorEvent] = []
        self._tenant_weights: dict[str, Any] = {}
        self._score_snapshots: list[dict[str, Any]] = []
        self._groups: dict[str, int] = {}
        self._alloc_seq = 0
        self._alloc_runs: dict[int, dict[str, Any]] = {}

    def ensure_group(self, group_id: str, group_priority: int) -> None:
        self._groups[group_id] = group_priority

    def list_groups(self) -> list[dict[str, Any]]:
        merged = dict(self._groups)
        for p in self._profiles.values():
            if p.group_id not in merged:
                merged[p.group_id] = p.group_priority
        return [
            {"group_id": gid, "group_priority": pri}
            for gid, pri in sorted(merged.items(), key=lambda x: x[0])
        ]

    def get_tenant_weights(self, group_id: str):
        from newton3.domain.tenant_weights import TenantWeights

        return self._tenant_weights.get(group_id, TenantWeights.default())

    def set_tenant_weights(self, group_id: str, weights: Any) -> None:
        self._tenant_weights[group_id] = weights

    def record_score_history(
        self,
        user_id: str,
        score: float,
        tier: str,
        event_type: str,
        detail: str,
        applied: bool,
        *,
        score_before: float | None = None,
    ) -> None:
        self._score_snapshots.append(
            {
                "user_id": user_id,
                "score": score,
                "score_before": score_before,
                "tier": tier,
                "event_type": event_type,
                "detail": detail,
                "applied": applied,
                "created_at": utcnow().isoformat(),
            }
        )

    def list_score_history(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = [r for r in reversed(self._score_snapshots) if r["user_id"] == user_id]
        rows = rows[: max(1, min(limit, 500))]
        return _attach_score_deltas(rows)

    def ensure_user(self, profile: UserProfile) -> None:
        self._profiles[profile.user_id] = profile
        if profile.user_id not in self._scores:
            self._scores[profile.user_id] = UserScoreState(user_id=profile.user_id)

    def get_profile(self, user_id: str) -> UserProfile | None:
        return self._profiles.get(user_id)

    def get_score_state(self, user_id: str) -> UserScoreState:
        if user_id not in self._scores:
            self._scores[user_id] = UserScoreState(user_id=user_id)
        return self._scores[user_id]

    def save_score_state(self, state: UserScoreState) -> None:
        self._scores[state.user_id] = replace(state)

    def log_event(self, event: BehaviorEvent) -> None:
        self._event_log.append(event)

    def recent_events(self, limit: int = 50, *, user_id: str | None = None) -> list[BehaviorEvent]:
        lim = max(1, limit)
        if user_id:
            uid = user_id.strip()
            matched = [e for e in reversed(self._event_log) if e.user_id == uid]
            return matched[:lim]
        chunk = self._event_log[-lim:]
        return list(reversed(chunk))

    def list_profiles(self) -> list[UserProfile]:
        return sorted(self._profiles.values(), key=lambda p: p.user_id)

    def record_space_allocation(
        self,
        pool_user_ids: list[str],
        capacity: int,
        seed: int | None,
        winners: list[AllocationResult],
    ) -> int:
        self._alloc_seq += 1
        rid = self._alloc_seq
        winners_payload: list[dict[str, Any]] = []
        for w in winners:
            sc = self.get_score_state(w.user_id)
            winners_payload.append(
                {
                    "rank": w.rank,
                    "user_id": w.user_id,
                    "explain": w.explain,
                    "behavior_score": sc.score,
                    "tier": tier_for_score(sc.score).value,
                }
            )
        self._alloc_runs[rid] = {
            "id": rid,
            "created_at": utcnow().isoformat(),
            "seed": seed,
            "capacity": capacity,
            "pool_user_ids": list(pool_user_ids),
            "winners": winners_payload,
        }
        return rid

    def list_space_allocations(self, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 500))
        rows = sorted(self._alloc_runs.values(), key=lambda r: r["id"], reverse=True)
        return rows[:lim]

    def get_space_allocation(self, run_id: int) -> dict[str, Any] | None:
        return self._alloc_runs.get(run_id)

    def clear_all_data(self) -> None:
        """Wipe users, scores, events, groups, tenant overrides, and score history."""
        self._profiles.clear()
        self._scores.clear()
        self._event_log.clear()
        self._tenant_weights.clear()
        self._score_snapshots.clear()
        self._groups.clear()
        self._alloc_seq = 0
        self._alloc_runs.clear()
