import os
from pathlib import Path

import pytest

from newton3.persistence.store import InMemoryStore
from newton3.persistence.store_factory import admin_enabled, make_store, store_kind
from newton3.persistence.sqlite_store import SqliteStore


def test_store_kind_default_sqlite(monkeypatch):
    monkeypatch.delenv("NEWTON3_STORE", raising=False)
    assert store_kind() == "sqlite"


def test_make_store_memory(monkeypatch):
    monkeypatch.setenv("NEWTON3_STORE", "memory")
    st = make_store()
    assert isinstance(st, InMemoryStore)


def test_make_store_sqlite_path(monkeypatch, tmp_path):
    db = tmp_path / "factory.db"
    monkeypatch.setenv("NEWTON3_STORE", "sqlite")
    monkeypatch.setenv("NEWTON3_DB_PATH", str(db))
    st = make_store()
    assert isinstance(st, SqliteStore)
    assert Path(st._path) == db.resolve()


def test_admin_enabled_default_true(monkeypatch):
    monkeypatch.delenv("NEWTON3_ADMIN_ENABLED", raising=False)
    assert admin_enabled() is True


def test_admin_enabled_false(monkeypatch):
    monkeypatch.setenv("NEWTON3_ADMIN_ENABLED", "false")
    assert admin_enabled() is False
