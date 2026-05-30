"""Persistence adapters: in-memory, SQLite (local), DynamoDB (AWS)."""

from newton3.persistence.store import InMemoryStore, ScoreStore
from newton3.persistence.store_factory import admin_enabled, make_store, store_kind

__all__ = [
    "InMemoryStore",
    "ScoreStore",
    "admin_enabled",
    "make_store",
    "store_kind",
]
