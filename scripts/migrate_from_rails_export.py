#!/usr/bin/env python3
"""
Rails → AWS migration (Phase 1).

Reads anonymized CSV exports (no Wayleadr credentials or production DB required).
Idempotent: safe to re-run; upserts users/groups and optionally replays events.

Usage (local prototype store — dry run):
  python scripts/migrate_from_rails_export.py --dir fixtures/migration --dry-run

Usage (deployed DynamoDB after ``sam deploy``):
  export AWS_REGION=eu-west-1
  export NEWTON3_DDB_USERS_TABLE=newton3-dev-users-scores
  export NEWTON3_DDB_EVENTS_TABLE=newton3-dev-behavior-events
  export NEWTON3_DDB_GROUPS_TABLE=newton3-dev-groups
  export NEWTON3_DDB_TENANT_TABLE=newton3-dev-tenant-config
  export NEWTON3_DDB_ALLOC_TABLE=newton3-dev-allocation-runs
  python scripts/migrate_from_rails_export.py --dir fixtures/migration --backend dynamodb

Usage (local SQLite — same CSVs as AWS migration):
  python scripts/migrate_from_rails_export.py --dir fixtures/migration --backend sqlite --db ./data/newton3.db

CSV formats (headers required):
  groups.csv: group_id,group_priority
  users.csv: user_id,user_name(optional),group_id,group_priority,user_priority
  events.csv: event_type,user_id,timestamp(optional ISO),payload_json(optional)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from newton3.domain.event_processor import process_event, seed_users
from newton3.domain.models import BehaviorEvent, UserProfile, utcnow
from newton3.persistence.store import InMemoryStore


@dataclass
class MigrationAudit:
    groups: int = 0
    users: int = 0
    events_applied: int = 0
    events_skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    return datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))


def run_migration(store, directory: Path, *, replay_events: bool) -> MigrationAudit:
    audit = MigrationAudit()
    groups_path = directory / "groups.csv"
    users_path = directory / "users.csv"
    events_path = directory / "events.csv"

    eg = getattr(store, "ensure_group", None)
    for row in _load_csv(groups_path):
        gid = (row.get("group_id") or "").strip()
        if not gid:
            continue
        gp = int(row.get("group_priority") or 100)
        if callable(eg):
            eg(gid, gp)
        audit.groups += 1

    profiles: list[UserProfile] = []
    for row in _load_csv(users_path):
        uid = (row.get("user_id") or "").strip()
        gid = (row.get("group_id") or "default").strip()
        if not uid:
            continue
        profiles.append(
            UserProfile(
                uid,
                gid,
                group_priority=int(row.get("group_priority") or 100),
                user_priority=int(row.get("user_priority") or 100),
                user_name=(row.get("user_name") or "").strip(),
            )
        )
    seed_users(store, profiles)
    audit.users = len(profiles)

    if replay_events:
        for row in _load_csv(events_path):
            uid = (row.get("user_id") or "").strip()
            et = (row.get("event_type") or "").strip()
            if not uid or not et:
                audit.events_skipped += 1
                continue
            if store.get_profile(uid) is None:
                audit.errors.append(f"event for unknown user {uid}")
                audit.events_skipped += 1
                continue
            payload_raw = row.get("payload_json") or "{}"
            try:
                payload = json.loads(payload_raw) if payload_raw.strip() else {}
            except json.JSONDecodeError:
                payload = {}
                audit.errors.append(f"bad payload for {uid}/{et}")
            ev = BehaviorEvent(et, uid, timestamp=_parse_ts(row.get("timestamp")), payload=payload)
            r = process_event(store, ev)
            if r.applied:
                audit.events_applied += 1
            else:
                audit.events_skipped += 1
            if getattr(store, "log_migration_audit", None):
                store.log_migration_audit(uid, et, r.detail)

    return audit


def main() -> int:
    p = argparse.ArgumentParser(description="Newton 3 Rails CSV → AWS migration")
    p.add_argument("--dir", type=Path, default=ROOT / "fixtures" / "migration")
    p.add_argument(
        "--backend",
        choices=("memory", "sqlite", "dynamodb"),
        default="memory",
        help="memory=dry parse target; sqlite=local DB; dynamodb=deployed tables",
    )
    p.add_argument("--dry-run", action="store_true", help="Parse only; no writes")
    p.add_argument("--no-events", action="store_true", help="Skip events.csv replay")
    p.add_argument("--db", default=None, help="SQLite path when --backend sqlite")
    p.add_argument("--stage", default="dev", help="SAM stage suffix for default table names")
    p.add_argument("--region", default=None)
    args = p.parse_args()

    if args.dry_run:
        audit = run_migration(InMemoryStore(), args.dir, replay_events=not args.no_events)
        print(json.dumps({"dry_run": True, "audit": audit.__dict__}, indent=2))
        return 0

    if args.backend == "dynamodb":
        import os

        if args.region:
            os.environ["AWS_DEFAULT_REGION"] = args.region
        stage = args.stage
        os.environ.setdefault("NEWTON3_DDB_USERS_TABLE", f"newton3-{stage}-users-scores")
        os.environ.setdefault("NEWTON3_DDB_EVENTS_TABLE", f"newton3-{stage}-behavior-events")
        os.environ.setdefault("NEWTON3_DDB_GROUPS_TABLE", f"newton3-{stage}-groups")
        os.environ.setdefault("NEWTON3_DDB_TENANT_TABLE", f"newton3-{stage}-tenant-config")
        os.environ.setdefault("NEWTON3_DDB_ALLOC_TABLE", f"newton3-{stage}-allocation-runs")
        from newton3.persistence.dynamodb_store import DynamoDBStore

        store = DynamoDBStore()
    elif args.backend == "sqlite":
        import os
        from pathlib import Path as _Path

        from newton3.persistence.sqlite_store import SqliteStore, default_sqlite_path

        db = _Path(args.db).expanduser().resolve() if args.db else default_sqlite_path()
        os.environ["NEWTON3_DB_PATH"] = str(db)
        store = SqliteStore(db)
    else:
        store = InMemoryStore()

    audit = run_migration(store, args.dir, replay_events=not args.no_events)
    out = {
        "completed_at": utcnow().isoformat(),
        "backend": args.backend,
        "directory": str(args.dir.resolve()),
        "audit": audit.__dict__,
    }
    print(json.dumps(out, indent=2))
    return 1 if audit.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
