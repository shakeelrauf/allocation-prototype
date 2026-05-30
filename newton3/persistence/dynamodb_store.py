"""DynamoDB-backed ScoreStore — AWS Phase 1 data layer (single-table per entity type)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from newton3.domain.models import AllocationResult, BehaviorEvent, UserProfile, UserScoreState, tier_for_score, utcnow
from newton3.domain.tenant_weights import TenantWeights

try:
    import boto3
    from boto3.dynamodb.conditions import Key
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore
    Key = None  # type: ignore


def _table_names() -> dict[str, str]:
    prefix = os.environ.get("NEWTON3_DDB_PREFIX", "newton3")
    return {
        "users": os.environ.get("NEWTON3_DDB_USERS_TABLE", f"{prefix}-users-scores"),
        "events": os.environ.get("NEWTON3_DDB_EVENTS_TABLE", f"{prefix}-behavior-events"),
        "tenant": os.environ.get("NEWTON3_DDB_TENANT_TABLE", f"{prefix}-tenant-config"),
        "groups": os.environ.get("NEWTON3_DDB_GROUPS_TABLE", f"{prefix}-groups"),
        "allocations": os.environ.get("NEWTON3_DDB_ALLOC_TABLE", f"{prefix}-allocation-runs"),
    }


def _pk_user(user_id: str) -> str:
    return f"USER#{user_id}"


def _pk_group(group_id: str) -> str:
    return f"GROUP#{group_id}"


def _dt_to_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _str_to_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


def _float(v: Any) -> float:
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _event_sk(ts: datetime) -> str:
    """Sortable SK: newest first when querying with ScanIndexForward=False."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    inv = 9999999999 - int(ts.timestamp())
    return f"EVENT#{inv:010d}#{uuid.uuid4().hex[:8]}"


class DynamoDBStore:
    """
    Production store aligned with Phase 1 design doc.

    Tables (see ``infra/sam/template.yaml``):
    - users-scores: PK ``USER#{id}``, SK ``PROFILE`` | ``SCORE`` | ``REWARD#{ts}``
    - behavior-events: PK ``USER#{id}``, SK ``EVENT#...``
    - tenant-config: PK ``GROUP#{id}``, SK ``WEIGHTS``
    - groups: PK ``GROUP#{id}``, SK ``META``
    - allocation-runs: PK ``RUN#{id}``, SK ``META`` | ``WINNER#{rank}``
    """

    def __init__(self, *, resource: Any = None, tables: dict[str, str] | None = None) -> None:
        if boto3 is None:
            raise RuntimeError("boto3 required for DynamoDBStore (pip install boto3)")
        self._tables = tables or _table_names()
        self._ddb = resource or boto3.resource("dynamodb")
        self._users = self._ddb.Table(self._tables["users"])
        self._events = self._ddb.Table(self._tables["events"])
        self._tenant = self._ddb.Table(self._tables["tenant"])
        self._groups = self._ddb.Table(self._tables["groups"])
        self._alloc = self._ddb.Table(self._tables["allocations"])
        self._alloc_seq = 0

    def ensure_group(self, group_id: str, group_priority: int) -> None:
        self._groups.put_item(
            Item={
                "pk": _pk_group(group_id),
                "sk": "META",
                "group_id": group_id,
                "group_priority": group_priority,
            }
        )

    def list_groups(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        resp = self._groups.scan()
        for it in resp.get("Items", []):
            if it.get("sk") == "META":
                out.append(
                    {
                        "group_id": it["group_id"],
                        "group_priority": int(it["group_priority"]),
                    }
                )
        while resp.get("LastEvaluatedKey"):
            resp = self._groups.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            for it in resp.get("Items", []):
                if it.get("sk") == "META":
                    out.append(
                        {
                            "group_id": it["group_id"],
                            "group_priority": int(it["group_priority"]),
                        }
                    )
        return sorted(out, key=lambda x: x["group_id"])

    def get_tenant_weights(self, group_id: str) -> TenantWeights:
        row = self._tenant.get_item(Key={"pk": _pk_group(group_id), "sk": "WEIGHTS"}).get("Item")
        if not row:
            return TenantWeights.default()
        raw = json.loads(row.get("weights_json", "{}"))
        return TenantWeights.from_dict(raw) if raw else TenantWeights.default()

    def set_tenant_weights(self, group_id: str, weights: TenantWeights) -> None:
        self._tenant.put_item(
            Item={
                "pk": _pk_group(group_id),
                "sk": "WEIGHTS",
                "group_id": group_id,
                "weights_json": json.dumps(weights.to_dict()),
            }
        )

    def ensure_user(self, profile: UserProfile) -> None:
        pk = _pk_user(profile.user_id)
        now = _dt_to_str(utcnow())
        self._users.put_item(
            Item={
                "pk": pk,
                "sk": "PROFILE",
                "user_id": profile.user_id,
                "group_id": profile.group_id,
                "group_priority": profile.group_priority,
                "user_priority": profile.user_priority,
                "user_name": (profile.user_name or "").strip(),
            }
        )
        existing = self._users.get_item(Key={"pk": pk, "sk": "SCORE"}).get("Item")
        if not existing:
            self._users.put_item(
                Item={
                    "pk": pk,
                    "sk": "SCORE",
                    "user_id": profile.user_id,
                    "score": Decimal("100"),
                    "last_penalty_at": None,
                    "last_decay_at": None,
                    "updated_at": now,
                    "reward_grants_json": "[]",
                }
            )

    def get_profile(self, user_id: str) -> UserProfile | None:
        row = self._users.get_item(Key={"pk": _pk_user(user_id), "sk": "PROFILE"}).get("Item")
        if not row:
            return None
        return UserProfile(
            row["user_id"],
            row["group_id"],
            group_priority=int(row["group_priority"]),
            user_priority=int(row["user_priority"]),
            user_name=(row.get("user_name") or "").strip(),
        )

    def _grants_from_row(self, row: dict[str, Any]) -> list[tuple[datetime, float]]:
        raw = json.loads(row.get("reward_grants_json", "[]"))
        grants: list[tuple[datetime, float]] = []
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                ts = _str_to_dt(str(item[0]))
                if ts:
                    grants.append((ts, float(item[1])))
        return grants

    def _grants_to_json(self, grants: list[tuple[datetime, float]]) -> str:
        return json.dumps([[ _dt_to_str(ts), pts] for ts, pts in grants])

    def get_score_state(self, user_id: str) -> UserScoreState:
        row = self._users.get_item(Key={"pk": _pk_user(user_id), "sk": "SCORE"}).get("Item")
        if not row:
            return UserScoreState(user_id=user_id)
        grants = self._grants_from_row(row)
        return UserScoreState(
            user_id=user_id,
            score=_float(row.get("score", 100)),
            last_penalty_at=_str_to_dt(row.get("last_penalty_at")),
            last_decay_at=_str_to_dt(row.get("last_decay_at")),
            updated_at=_str_to_dt(row.get("updated_at")) or utcnow(),
            reward_grants=grants,
        )

    def save_score_state(self, state: UserScoreState) -> None:
        pk = _pk_user(state.user_id)
        self._users.put_item(
            Item={
                "pk": pk,
                "sk": "SCORE",
                "user_id": state.user_id,
                "score": Decimal(str(round(state.score, 4))),
                "last_penalty_at": _dt_to_str(state.last_penalty_at),
                "last_decay_at": _dt_to_str(state.last_decay_at),
                "updated_at": _dt_to_str(state.updated_at or utcnow()),
                "reward_grants_json": self._grants_to_json(state.reward_grants),
            }
        )

    def log_event(self, event: BehaviorEvent) -> None:
        ts = event.timestamp or utcnow()
        et = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
        self._events.put_item(
            Item={
                "pk": _pk_user(event.user_id),
                "sk": _event_sk(ts),
                "user_id": event.user_id,
                "event_type": et,
                "payload_json": json.dumps(event.payload or {}),
                "timestamp": _dt_to_str(ts),
            }
        )

    def recent_events(self, limit: int = 50, *, user_id: str | None = None) -> list[BehaviorEvent]:
        lim = max(1, min(limit, 500))
        out: list[BehaviorEvent] = []
        uid = (user_id or "").strip()
        resp = self._events.scan(Limit=lim * 8)
        items = list(resp.get("Items", []))
        while resp.get("LastEvaluatedKey") and len(items) < lim * 20:
            resp = self._events.scan(
                ExclusiveStartKey=resp["LastEvaluatedKey"],
                Limit=lim * 8,
            )
            items.extend(resp.get("Items", []))
        if uid:
            items = [it for it in items if it.get("user_id") == uid]
        items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        for it in items[:lim]:
            payload = json.loads(it.get("payload_json", "{}"))
            out.append(
                BehaviorEvent(
                    it["event_type"],
                    it["user_id"],
                    timestamp=_str_to_dt(it.get("timestamp")),
                    payload=payload,
                )
            )
        return out

    def list_profiles(self) -> list[UserProfile]:
        out: list[UserProfile] = []
        resp = self._users.scan()
        for it in resp.get("Items", []):
            if it.get("sk") == "PROFILE":
                out.append(
                    UserProfile(
                        it["user_id"],
                        it["group_id"],
                        group_priority=int(it["group_priority"]),
                        user_priority=int(it["user_priority"]),
                        user_name=(it.get("user_name") or "").strip(),
                    )
                )
        while resp.get("LastEvaluatedKey"):
            resp = self._users.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            for it in resp.get("Items", []):
                if it.get("sk") == "PROFILE":
                    out.append(
                        UserProfile(
                            it["user_id"],
                            it["group_id"],
                            group_priority=int(it["group_priority"]),
                            user_priority=int(it["user_priority"]),
                            user_name=(it.get("user_name") or "").strip(),
                        )
                    )
        return sorted(out, key=lambda p: p.user_id)

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
        ts = utcnow()
        self._events.put_item(
            Item={
                "pk": _pk_user(user_id),
                "sk": _event_sk(ts),
                "user_id": user_id,
                "event_type": f"snapshot.{event_type}",
                "payload_json": json.dumps(
                    {
                        "score": score,
                        "score_before": score_before,
                        "tier": tier,
                        "detail": detail,
                        "applied": applied,
                    }
                ),
                "timestamp": _dt_to_str(ts),
            }
        )

    def list_score_history(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 500))
        pk = _pk_user(user_id)
        resp = self._events.query(
            KeyConditionExpression=Key("pk").eq(pk),
            ScanIndexForward=False,
            Limit=lim * 3,
        )
        rows: list[dict[str, Any]] = []
        for it in resp.get("Items", []):
            et = it.get("event_type", "")
            if not et.startswith("snapshot."):
                continue
            payload = json.loads(it.get("payload_json", "{}"))
            rows.append(
                {
                    "user_id": user_id,
                    "score": payload.get("score"),
                    "score_before": payload.get("score_before"),
                    "tier": payload.get("tier"),
                    "event_type": et.replace("snapshot.", "", 1),
                    "detail": payload.get("detail"),
                    "applied": payload.get("applied"),
                    "created_at": it.get("timestamp"),
                }
            )
            if len(rows) >= lim:
                break
        return _attach_score_deltas(rows)

    def record_space_allocation(
        self,
        pool_user_ids: list[str],
        capacity: int,
        seed: int | None,
        winners: list[AllocationResult],
    ) -> int:
        rid = int(uuid.uuid4().int % 2_000_000_000) + 1
        pk = f"RUN#{rid}"
        now = _dt_to_str(utcnow())
        self._alloc.put_item(
            Item={
                "pk": pk,
                "sk": "META",
                "id": rid,
                "created_at": now,
                "seed": seed,
                "capacity": capacity,
                "pool_json": json.dumps(pool_user_ids),
            }
        )
        for w in winners:
            sc = self.get_score_state(w.user_id)
            self._alloc.put_item(
                Item={
                    "pk": pk,
                    "sk": f"WINNER#{w.rank:04d}",
                    "rank": w.rank,
                    "user_id": w.user_id,
                    "explain": w.explain,
                    "behavior_score": Decimal(str(sc.score)),
                    "tier": tier_for_score(sc.score).value,
                }
            )
        return rid

    def list_space_allocations(self, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 500))
        resp = self._alloc.scan()
        metas = [it for it in resp.get("Items", []) if it.get("sk") == "META"]
        while resp.get("LastEvaluatedKey"):
            resp = self._alloc.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            metas.extend(it for it in resp.get("Items", []) if it.get("sk") == "META")
        metas.sort(key=lambda x: int(x.get("id", 0)), reverse=True)
        out: list[dict[str, Any]] = []
        for m in metas[:lim]:
            rid = int(m["id"])
            pk = f"RUN#{rid}"
            wresp = self._alloc.query(
                KeyConditionExpression=Key("pk").eq(pk) & Key("sk").begins_with("WINNER#"),
            )
            winners = []
            for w in sorted(wresp.get("Items", []), key=lambda x: int(x.get("rank", 0))):
                winners.append(
                    {
                        "rank": int(w["rank"]),
                        "user_id": w["user_id"],
                        "explain": w["explain"],
                        "behavior_score": _float(w.get("behavior_score")),
                        "tier": w["tier"],
                    }
                )
            out.append(
                {
                    "id": rid,
                    "created_at": m.get("created_at"),
                    "seed": m.get("seed"),
                    "capacity": int(m.get("capacity", 0)),
                    "pool_user_ids": json.loads(m.get("pool_json", "[]")),
                    "winners": winners,
                }
            )
        return out

    def get_space_allocation(self, run_id: int) -> dict[str, Any] | None:
        rows = self.list_space_allocations(limit=500)
        for r in rows:
            if r["id"] == run_id:
                return r
        return None

    def clear_all_data(self) -> None:
        """Delete all items (demo reset). Use only in non-prod."""
        for table in (self._users, self._events, self._tenant, self._groups, self._alloc):
            resp = table.scan()
            with table.batch_writer() as batch:
                for it in resp.get("Items", []):
                    batch.delete_item(Key={"pk": it["pk"], "sk": it["sk"]})
            while resp.get("LastEvaluatedKey"):
                resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
                with table.batch_writer() as batch:
                    for it in resp.get("Items", []):
                        batch.delete_item(Key={"pk": it["pk"], "sk": it["sk"]})
