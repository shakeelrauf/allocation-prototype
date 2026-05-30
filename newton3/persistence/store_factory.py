"""Select persistence backend from environment (SQLite local, DynamoDB on AWS)."""

from __future__ import annotations

import os
from pathlib import Path

from newton3.persistence.store import ScoreStore


def store_kind() -> str:
    return os.environ.get("NEWTON3_STORE", "sqlite").strip().lower()


def admin_enabled() -> bool:
    """Operator/admin routes (reset, CSV import). Disable on public AWS console Lambda."""
    return os.environ.get("NEWTON3_ADMIN_ENABLED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def make_store() -> ScoreStore:
    kind = store_kind()
    if kind in ("dynamodb", "ddb", "aws"):
        from newton3.persistence.dynamodb_store import DynamoDBStore

        return DynamoDBStore()
    if kind in ("memory", "inmemory"):
        from newton3.persistence.store import InMemoryStore

        return InMemoryStore()
    # Default: SQLite for local / Docker
    from newton3.persistence.sqlite_store import SqliteStore, default_sqlite_path

    raw = os.environ.get("NEWTON3_DB_PATH")
    if raw:
        return SqliteStore(Path(raw).expanduser().resolve())
    return SqliteStore(default_sqlite_path())
