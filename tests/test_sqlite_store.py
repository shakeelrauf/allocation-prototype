import tempfile
from pathlib import Path

from newton3.domain.allocation_engine import allocate_spaces
from newton3.domain.models import BehaviorEvent, EventType, UserProfile, UserScoreState
from newton3.persistence.sqlite_store import SqliteStore
from newton3.persistence.store import InMemoryStore


def test_sqlite_roundtrip_scores_and_rewards():
    path = Path(tempfile.mkdtemp()) / "t.db"
    store = SqliteStore(path)
    store.ensure_user(UserProfile("u1", "g", group_priority=1, user_priority=2))
    st = store.get_score_state("u1")
    assert st.score == 100
    st.score = 91
    st.reward_grants.append((st.updated_at, 5.0))
    store.save_score_state(st)
    store.close()

    store2 = SqliteStore(path)
    try:
        st2 = store2.get_score_state("u1")
        assert st2.score == 91
        assert len(st2.reward_grants) == 1
        assert st2.reward_grants[0][1] == 5.0
    finally:
        store2.close()


def test_sqlite_logs_events():
    path = Path(tempfile.mkdtemp()) / "e.db"
    store = SqliteStore(path)
    try:
        store.log_event(BehaviorEvent(EventType.CARPOOL_DETECTED, "u9"))
        recent = store.recent_events(10)
        assert len(recent) == 1
        assert recent[0].user_id == "u9"
    finally:
        store.close()


def test_sqlite_clear_all_data():
    path = Path(tempfile.mkdtemp()) / "clear.db"
    store = SqliteStore(path)
    try:
        store.ensure_group("eng", 1)
        store.ensure_user(UserProfile("alice", "eng", group_priority=1, user_priority=5))
        store.log_event(BehaviorEvent(EventType.OFFENCE_REPORTED, "alice"))
        assert len(store.list_profiles()) == 1
        store.clear_all_data()
        assert store.list_profiles() == []
        assert store.list_groups() == []
        assert store.recent_events(5) == []
        assert store.list_space_allocations(5) == []
    finally:
        store.close()


def test_sqlite_space_allocation_persist_and_reload():
    path = Path(tempfile.mkdtemp()) / "alloc.db"
    store = SqliteStore(path)
    try:
        store.ensure_user(UserProfile("a", "g", 1, 1))
        store.ensure_user(UserProfile("b", "g", 1, 1))
        rows = allocate_spaces(store, ["a", "b"], capacity=1, seed=7)
        rid = store.record_space_allocation(["a", "b"], 1, 7, rows)
        assert rid >= 1
        got = store.get_space_allocation(rid)
        assert got is not None and len(got["winners"]) == 1
        assert got["pool_user_ids"] == ["a", "b"]
    finally:
        store.close()

    store2 = SqliteStore(path)
    try:
        lst = store2.list_space_allocations(10)
        assert len(lst) == 1
        assert lst[0]["winners"][0]["user_id"] in ("a", "b")
    finally:
        store2.close()


def test_inmemory_list_profiles():
    s = InMemoryStore()
    s.ensure_user(UserProfile("b", "g"))
    s.ensure_user(UserProfile("a", "g"))
    ids = [p.user_id for p in s.list_profiles()]
    assert ids == ["a", "b"]
