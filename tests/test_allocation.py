from allocation_engine import allocate_spaces, rank_users
from event_processor import seed_users
from models import UserProfile
from store import InMemoryStore


def _store_with_three() -> InMemoryStore:
    store = InMemoryStore()
    seed_users(
        store,
        [
            UserProfile("a", "g1", group_priority=1, user_priority=1),
            UserProfile("b", "g1", group_priority=1, user_priority=1),
            UserProfile("c", "g2", group_priority=2, user_priority=1),
        ],
    )
    return store


def test_group_priority_wins():
    store = _store_with_three()
    r = rank_users(store, ["a", "b", "c"], seed=99)
    assert {r[0].user_id, r[1].user_id} == {"a", "b"}
    assert r[2].user_id == "c"


def test_behavior_score_breaks_tie_within_group():
    store = InMemoryStore()
    seed_users(
        store,
        [
            UserProfile("a", "g1", group_priority=1, user_priority=1),
            UserProfile("b", "g1", group_priority=1, user_priority=1),
        ],
    )
    store.get_score_state("a").score = 120
    store.get_score_state("b").score = 90
    r = rank_users(store, ["a", "b"], seed=1)
    assert r[0].user_id == "a"


def test_allocate_capacity():
    store = _store_with_three()
    got = allocate_spaces(store, ["a", "b", "c"], capacity=2, seed=99)
    assert len(got) == 2


def test_restricted_after_eligible_never_wins_slot_if_alternative_exists():
    store = InMemoryStore()
    seed_users(
        store,
        [
            UserProfile("vip", "g1", group_priority=1, user_priority=1),
            UserProfile("ok", "g9", group_priority=9, user_priority=9),
        ],
    )
    store.get_score_state("vip").score = 40.0  # Restricted (<50)
    store.get_score_state("ok").score = 100.0  # Silver
    r = rank_users(store, ["vip", "ok"], seed=7)
    assert r[0].user_id == "ok"
    assert r[1].user_id == "vip"
    assert "not eligible" in r[1].explain
    got = allocate_spaces(store, ["vip", "ok"], capacity=1, seed=7)
    assert got[0].user_id == "ok"


def test_all_restricted_pool_still_allocates_among_themselves():
    store = InMemoryStore()
    seed_users(
        store,
        [
            UserProfile("x", "g1", group_priority=1, user_priority=2),
            UserProfile("y", "g1", group_priority=1, user_priority=9),
        ],
    )
    store.get_score_state("x").score = 40.0
    store.get_score_state("y").score = 45.0
    got = allocate_spaces(store, ["x", "y"], capacity=1, seed=1)
    assert got[0].user_id == "x"  # better user_priority within Restricted-only pool
