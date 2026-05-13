from allocation_engine import rank_users
from event_processor import seed_users
from models import UserProfile
from shadow_engine import rank_legacy
from store import InMemoryStore


def test_shadow_diff_detects_reorder_when_behaviour_differs():
    store = InMemoryStore()
    seed_users(
        store,
        [
            UserProfile("a", "g", group_priority=1, user_priority=1),
            UserProfile("b", "g", group_priority=1, user_priority=1),
        ],
    )
    store.get_score_state("a").score = 130
    store.get_score_state("b").score = 90

    mismatch = False
    for seed in range(80):
        newton = rank_users(store, ["a", "b"], seed=seed)
        legacy = rank_legacy(store, ["a", "b"], seed=seed)
        assert newton[0].user_id == "a"
        if legacy[0].user_id != newton[0].user_id:
            mismatch = True
            break
    assert mismatch, "mock-legacy ranking should sometimes disagree when behaviour separates users"
