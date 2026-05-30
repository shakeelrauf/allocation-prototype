"""SQLite-backed ScoreStore for local runs (single-file DB)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from newton3.domain.models import AllocationResult, BehaviorEvent, UserProfile, UserScoreState, tier_for_score, utcnow
from newton3.persistence.store import _attach_score_deltas
from newton3.domain.tenant_weights import TenantWeights

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    group_priority INTEGER NOT NULL,
    user_priority INTEGER NOT NULL,
    user_name TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scores (
    user_id TEXT PRIMARY KEY,
    score REAL NOT NULL DEFAULT 100,
    last_penalty_at TEXT,
    last_decay_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reward_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    points REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reward_user ON reward_grants (user_id);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events (timestamp DESC);

CREATE TABLE IF NOT EXISTS score_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    score REAL NOT NULL,
    tier TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    applied INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snap_user ON score_snapshots (user_id, id DESC);

CREATE TABLE IF NOT EXISTS tenant_config (
    group_id TEXT PRIMARY KEY,
    weights_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT PRIMARY KEY,
    group_priority INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS allocation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    seed INTEGER,
    capacity INTEGER NOT NULL,
    pool_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS allocation_winners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    explain TEXT NOT NULL,
    behavior_score REAL,
    tier TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES allocation_runs (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_alloc_runs_id ON allocation_runs (id DESC);
CREATE INDEX IF NOT EXISTS idx_alloc_winners_run ON allocation_winners (run_id, rank);
"""


def default_sqlite_path() -> Path:
    from newton3.paths import REPO_ROOT

    base = REPO_ROOT / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base / "newton3.db"


class SqliteStore:
    """Thread-safe SQLite store for local API/UI."""

    def __init__(self, path: str | Path | None = None) -> None:
        resolved = Path(path or default_sqlite_path()).expanduser().resolve()
        self._path = str(resolved)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._migrate_users_user_name()
        self._migrate_snapshots_score_before()
        self._conn.commit()

    def _migrate_users_user_name(self) -> None:
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(users)")}
        if "user_name" not in cols:
            self._conn.execute(
                "ALTER TABLE users ADD COLUMN user_name TEXT NOT NULL DEFAULT ''"
            )

    def _migrate_snapshots_score_before(self) -> None:
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(score_snapshots)")}
        if "score_before" not in cols:
            self._conn.execute(
                "ALTER TABLE score_snapshots ADD COLUMN score_before REAL"
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _dt_to_str(self, dt) -> str | None:
        if dt is None:
            return None
        return dt.isoformat()

    def _str_to_dt(self, s: str | None):
        if s is None:
            return None
        from datetime import datetime

        return datetime.fromisoformat(s)

    def ensure_user(self, profile: UserProfile) -> None:
        now = self._dt_to_str(utcnow())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO users (user_id, group_id, group_priority, user_priority, user_name)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    group_id = excluded.group_id,
                    group_priority = excluded.group_priority,
                    user_priority = excluded.user_priority,
                    user_name = excluded.user_name
                """,
                (
                    profile.user_id,
                    profile.group_id,
                    profile.group_priority,
                    profile.user_priority,
                    (profile.user_name or "").strip(),
                ),
            )
            self._conn.execute(
                """
                INSERT INTO scores (user_id, score, updated_at)
                VALUES (?, 100, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (profile.user_id, now),
            )
            self._conn.commit()

    def get_profile(self, user_id: str) -> UserProfile | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT user_id, group_id, group_priority, user_priority, user_name FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return UserProfile(
            row["user_id"],
            row["group_id"],
            group_priority=row["group_priority"],
            user_priority=row["user_priority"],
            user_name=(row["user_name"] or "").strip()
            if "user_name" in row.keys()
            else "",
        )

    def _load_reward_grants(self, user_id: str) -> list[tuple]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT granted_at, points FROM reward_grants WHERE user_id = ? ORDER BY granted_at",
                (user_id,),
            ).fetchall()
        return [(self._str_to_dt(r["granted_at"]), float(r["points"])) for r in rows]

    def get_score_state(self, user_id: str) -> UserScoreState:
        """Load persisted score or return a fresh in-memory default (matches InMemoryStore)."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT user_id, score, last_penalty_at, last_decay_at, updated_at
                FROM scores WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

        if row is None:
            return UserScoreState(user_id=user_id)

        grants = self._load_reward_grants(user_id)
        return UserScoreState(
            user_id=user_id,
            score=float(row["score"]),
            last_penalty_at=self._str_to_dt(row["last_penalty_at"])
            if row["last_penalty_at"]
            else None,
            last_decay_at=self._str_to_dt(row["last_decay_at"]) if row["last_decay_at"] else None,
            updated_at=self._str_to_dt(row["updated_at"]) or utcnow(),
            reward_grants=grants,
        )

    def save_score_state(self, state: UserScoreState) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO scores (user_id, score, last_penalty_at, last_decay_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    score = excluded.score,
                    last_penalty_at = excluded.last_penalty_at,
                    last_decay_at = excluded.last_decay_at,
                    updated_at = excluded.updated_at
                """,
                (
                    state.user_id,
                    state.score,
                    self._dt_to_str(state.last_penalty_at),
                    self._dt_to_str(state.last_decay_at),
                    self._dt_to_str(state.updated_at),
                ),
            )
            self._conn.execute("DELETE FROM reward_grants WHERE user_id = ?", (state.user_id,))
            for ts, pts in state.reward_grants:
                self._conn.execute(
                    "INSERT INTO reward_grants (user_id, granted_at, points) VALUES (?, ?, ?)",
                    (state.user_id, self._dt_to_str(ts), pts),
                )
            self._conn.commit()

    def log_event(self, event: BehaviorEvent) -> None:
        et = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
        ts = event.timestamp or utcnow()
        payload = json.dumps(event.payload or {})
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO events (user_id, event_type, payload_json, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (event.user_id, et, payload, self._dt_to_str(ts)),
            )
            self._conn.commit()

    def recent_events(self, limit: int = 50, *, user_id: str | None = None) -> list[BehaviorEvent]:
        lim = max(1, min(limit, 500))
        with self._lock:
            if user_id and user_id.strip():
                rows = self._conn.execute(
                    """
                    SELECT user_id, event_type, payload_json, timestamp
                    FROM events WHERE user_id = ? ORDER BY id DESC LIMIT ?
                    """,
                    (user_id.strip(), lim),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT user_id, event_type, payload_json, timestamp
                    FROM events ORDER BY id DESC LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
        out: list[BehaviorEvent] = []
        for r in rows:
            payload = json.loads(r["payload_json"] or "{}")
            out.append(
                BehaviorEvent(
                    r["event_type"],
                    r["user_id"],
                    timestamp=self._str_to_dt(r["timestamp"]),
                    payload=payload,
                )
            )
        return out

    def list_profiles(self) -> list[UserProfile]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT user_id, group_id, group_priority, user_priority, user_name FROM users ORDER BY user_id"
            ).fetchall()
        return [
            UserProfile(
                r["user_id"],
                r["group_id"],
                group_priority=r["group_priority"],
                user_priority=r["user_priority"],
                user_name=(r["user_name"] or "").strip(),
            )
            for r in rows
        ]

    def ensure_group(self, group_id: str, group_priority: int) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO groups (group_id, group_priority)
                VALUES (?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    group_priority = excluded.group_priority
                """,
                (group_id, group_priority),
            )
            self._conn.commit()

    def record_space_allocation(
        self,
        pool_user_ids: list[str],
        capacity: int,
        seed: int | None,
        winners: list[AllocationResult],
    ) -> int:
        pool_json = json.dumps(pool_user_ids)
        now = self._dt_to_str(utcnow())
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO allocation_runs (created_at, seed, capacity, pool_json)
                VALUES (?, ?, ?, ?)
                """,
                (now, seed, capacity, pool_json),
            )
            run_id = int(cur.lastrowid)
            for w in winners:
                sc = self.get_score_state(w.user_id)
                tier = tier_for_score(sc.score).value
                self._conn.execute(
                    """
                    INSERT INTO allocation_winners
                        (run_id, rank, user_id, explain, behavior_score, tier)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, w.rank, w.user_id, w.explain, sc.score, tier),
                )
            self._conn.commit()
        return run_id

    def list_space_allocations(self, limit: int = 50) -> list[dict]:
        lim = max(1, min(limit, 500))
        with self._lock:
            runs = self._conn.execute(
                """
                SELECT id, created_at, seed, capacity, pool_json
                FROM allocation_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()
            if not runs:
                return []
            run_ids = [int(r["id"]) for r in runs]
            placeholders = ",".join("?" * len(run_ids))
            wrows = self._conn.execute(
                f"""
                SELECT run_id, rank, user_id, explain, behavior_score, tier
                FROM allocation_winners
                WHERE run_id IN ({placeholders})
                ORDER BY run_id, rank
                """,
                run_ids,
            ).fetchall()
        by_run: dict[int, list[dict]] = {}
        for wr in wrows:
            rid = int(wr["run_id"])
            by_run.setdefault(rid, []).append(
                {
                    "rank": wr["rank"],
                    "user_id": wr["user_id"],
                    "explain": wr["explain"],
                    "behavior_score": wr["behavior_score"],
                    "tier": wr["tier"],
                }
            )
        return [
            {
                "id": int(r["id"]),
                "created_at": r["created_at"],
                "seed": r["seed"],
                "capacity": r["capacity"],
                "pool_user_ids": json.loads(r["pool_json"] or "[]"),
                "winners": by_run.get(int(r["id"]), []),
            }
            for r in runs
        ]

    def get_space_allocation(self, run_id: int) -> dict | None:
        with self._lock:
            r = self._conn.execute(
                """
                SELECT id, created_at, seed, capacity, pool_json
                FROM allocation_runs WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
            if r is None:
                return None
            wrows = self._conn.execute(
                """
                SELECT rank, user_id, explain, behavior_score, tier
                FROM allocation_winners
                WHERE run_id = ?
                ORDER BY rank
                """,
                (run_id,),
            ).fetchall()
        winners = [
            {
                "rank": wr["rank"],
                "user_id": wr["user_id"],
                "explain": wr["explain"],
                "behavior_score": wr["behavior_score"],
                "tier": wr["tier"],
            }
            for wr in wrows
        ]
        return {
            "id": int(r["id"]),
            "created_at": r["created_at"],
            "seed": r["seed"],
            "capacity": r["capacity"],
            "pool_user_ids": json.loads(r["pool_json"] or "[]"),
            "winners": winners,
        }

    def list_groups(self) -> list[dict]:
        merged: dict[str, int] = {}
        with self._lock:
            for r in self._conn.execute("SELECT group_id, group_priority FROM groups"):
                merged[r["group_id"]] = r["group_priority"]
            for r in self._conn.execute(
                "SELECT DISTINCT group_id, group_priority FROM users ORDER BY group_id"
            ):
                gid = r["group_id"]
                if gid not in merged:
                    merged[gid] = r["group_priority"]
        return [
            {"group_id": gid, "group_priority": pri}
            for gid, pri in sorted(merged.items(), key=lambda x: x[0])
        ]

    def get_tenant_weights(self, group_id: str) -> TenantWeights:
        with self._lock:
            row = self._conn.execute(
                "SELECT weights_json FROM tenant_config WHERE group_id = ?",
                (group_id,),
            ).fetchone()
        if row is None:
            return TenantWeights.default()
        raw = json.loads(row["weights_json"] or "{}")
        return TenantWeights.from_dict(raw)

    def set_tenant_weights(self, group_id: str, weights: TenantWeights) -> None:
        payload = json.dumps(weights.to_dict())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO tenant_config (group_id, weights_json)
                VALUES (?, ?)
                ON CONFLICT(group_id) DO UPDATE SET weights_json = excluded.weights_json
                """,
                (group_id, payload),
            )
            self._conn.commit()

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
        now = self._dt_to_str(utcnow())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO score_snapshots
                    (user_id, score, score_before, tier, event_type, detail, applied, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    score,
                    score_before,
                    tier,
                    event_type,
                    detail,
                    1 if applied else 0,
                    now,
                ),
            )
            self._conn.commit()

    def list_score_history(self, user_id: str, limit: int = 50) -> list[dict]:
        lim = max(1, min(limit, 500))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT user_id, score, score_before, tier, event_type, detail, applied, created_at
                FROM score_snapshots
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, lim),
            ).fetchall()
        base = [
            {
                "user_id": r["user_id"],
                "score": r["score"],
                "score_before": r["score_before"],
                "tier": r["tier"],
                "event_type": r["event_type"],
                "detail": r["detail"],
                "applied": bool(r["applied"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        return _attach_score_deltas(base)

    def clear_all_data(self) -> None:
        """Delete every row (users, scores, events, groups, tenant config, history)."""
        tables = (
            "allocation_winners",
            "allocation_runs",
            "reward_grants",
            "score_snapshots",
            "events",
            "scores",
            "users",
            "tenant_config",
            "groups",
        )
        with self._lock:
            for t in tables:
                self._conn.execute(f"DELETE FROM {t}")
            self._conn.commit()
