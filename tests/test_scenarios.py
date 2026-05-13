from models import BehaviorEvent, EventType, UserProfile
from event_processor import process_event, seed_users
from store import InMemoryStore


def test_no_show_then_decay_recovery():
    store = InMemoryStore()
    seed_users(store, [UserProfile("alice", "eng", group_priority=1, user_priority=5)])
    process_event(store, BehaviorEvent(EventType.UNUSED_BOOKING, "alice"))
    assert store.get_score_state("alice").score == 97
    process_event(store, BehaviorEvent(EventType.WEEKLY_DECAY, "alice", payload={"weeks": 2}))
    assert store.get_score_state("alice").score == 100


def test_offence_and_carpool_net():
    store = InMemoryStore()
    seed_users(store, [UserProfile("bob", "eng", group_priority=1, user_priority=5)])
    process_event(store, BehaviorEvent(EventType.CARPOOL_DETECTED, "bob"))
    process_event(store, BehaviorEvent(EventType.OFFENCE_REPORTED, "bob"))
    assert store.get_score_state("bob").score == 100
