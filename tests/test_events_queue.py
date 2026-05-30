import json

from newton3.domain.event_processor import seed_users
from newton3.services.events_queue import (
    collect_incoming_records,
    process_incoming_records,
    should_enqueue_http_event,
)
from newton3.domain.models import BehaviorEvent, UserProfile
from newton3.persistence.store import InMemoryStore


def test_collect_sqs_eventbridge_envelope():
    body = {
        "version": "0",
        "source": "newton3.booking",
        "detail-type": "BehaviorEvent",
        "detail": {"event_type": "unused_booking", "user_id": "bob", "payload": {}},
    }
    event = {"Records": [{"eventSource": "aws:sqs", "body": json.dumps(body)}]}
    rows = collect_incoming_records(event)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "unused_booking"
    assert rows[0]["user_id"] == "bob"


def test_process_decay_batch():
    st = InMemoryStore()
    seed_users(st, [UserProfile("a", "g"), UserProfile("b", "g")])
    results = process_incoming_records(st, [{"source": "newton3.decay", "weeks": 1}])
    assert len(results) == 2


def test_should_enqueue_http_when_async_and_no_http_sync(monkeypatch):
    monkeypatch.setenv("NEWTON3_EVENTS_ASYNC", "true")
    monkeypatch.setenv("NEWTON3_EVENTS_QUEUE_URL", "https://sqs.example/queue")
    monkeypatch.setenv("NEWTON3_EVENTS_HTTP_SYNC", "false")
    assert should_enqueue_http_event() is True


def test_should_not_enqueue_when_http_sync(monkeypatch):
    monkeypatch.setenv("NEWTON3_EVENTS_ASYNC", "true")
    monkeypatch.setenv("NEWTON3_EVENTS_QUEUE_URL", "https://sqs.example/queue")
    monkeypatch.setenv("NEWTON3_EVENTS_HTTP_SYNC", "true")
    assert should_enqueue_http_event() is False


def test_scoring_handler_integration_shape():
    st = InMemoryStore()
    st.ensure_user(UserProfile("bob", "g", 1, 1))
    rows = collect_incoming_records(
        {"Records": [{"eventSource": "aws:sqs", "body": json.dumps({"event_type": "unused_booking", "user_id": "bob"})}]}
    )
    out = process_incoming_records(st, rows)
    assert out[0]["score_after"] == 97
    assert out[0]["score_delta"] == -3
