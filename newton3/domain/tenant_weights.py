"""Per-tenant (group) scoring weights — merged with defaults for dynamic config."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from newton3.persistence.store import ScoreStore


@dataclass(frozen=True)
class TenantWeights:
    no_show: float = 3.0
    free_space: float = 1.0
    offence: float = 5.0
    carpool: float = 5.0
    decay_per_week: float = 2.0
    reward_cap_total: float = 20.0
    reward_cap_window_days: int = 28

    @staticmethod
    def default() -> TenantWeights:
        return TenantWeights()

    def to_dict(self) -> dict[str, Any]:
        return {
            "no_show": self.no_show,
            "free_space": self.free_space,
            "offence": self.offence,
            "carpool": self.carpool,
            "decay_per_week": self.decay_per_week,
            "reward_cap_total": self.reward_cap_total,
            "reward_cap_window_days": self.reward_cap_window_days,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TenantWeights:
        d = TenantWeights.default().to_dict()
        for k in d:
            if k in raw:
                v = raw[k]
                d[k] = int(v) if k == "reward_cap_window_days" else float(v)
        return cls(**d)  # type: ignore[arg-type]


def resolve_weights(store: ScoreStore, user_id: str) -> TenantWeights:
    prof = store.get_profile(user_id)
    gid = prof.group_id if prof else None
    get_tw = getattr(store, "get_tenant_weights", None)
    if gid and callable(get_tw):
        return get_tw(gid)
    return TenantWeights.default()
