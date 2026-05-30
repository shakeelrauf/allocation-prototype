"""SQS enqueue + batch scoring for async behaviour events (AWS)."""

from __future__ import annotations

import json
import os
from typing import Any

from newton3.domain.event_processor import ProcessResult, process_event
from newton3.domain.models import BehaviorEvent
from newton3.persistence.store import ScoreStore


def events_async_enabled() -> bool:
    return os.environ.get("NEWTON3_EVENTS_ASYNC", "").strip().lower() in ("1", "true", "yes")


def events_http_sync_enabled() -> bool:
    """When true, HTTP POST /api/events runs process_event immediately (UI deltas)."""
    return os.environ.get("NEWTON3_EVENTS_HTTP_SYNC", "true").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def events_queue_url() -> str | None:
    url = (os.environ.get("NEWTON3_EVENTS_QUEUE_URL") or "").strip()
    return url or None


def should_enqueue_http_event() -> bool:
    return events_async_enabled() and bool(events_queue_url()) and not events_http_sync_enabled()


def enqueue_behavior_event(
    event_type: str,
    user_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = events_queue_url()
    if not url:
        raise RuntimeError("NEWTON3_EVENTS_QUEUE_URL is not set")
    body = {
        "event_type": event_type,
        "user_id": user_id,
        "payload": payload or {},
    }
    import boto3

    sqs = boto3.client("sqs")
    resp = sqs.send_message(QueueUrl=url, MessageBody=json.dumps(body))
    return {
        "queued": True,
        "message_id": resp.get("MessageId"),
        "event_type": event_type,
        "user_id": user_id,
    }


def _unwrap_payload(raw: Any) -> dict[str, Any] | None:
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    if "detail" in raw and isinstance(raw["detail"], dict):
        return raw["detail"]
    if "body" in raw and isinstance(raw["body"], str):
        return _unwrap_payload(raw["body"])
    return raw


def collect_incoming_records(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Lambda event (SQS, EventBridge, schedule, API) into scoring payloads."""
    records: list[dict[str, Any]] = []

    if event.get("source") in ("aws.events", "newton3.decay") or event.get("detail-type") == "Scheduled Event":
        weeks = 1
        if isinstance(event.get("detail"), dict):
            weeks = int(event["detail"].get("weeks", 1))
        else:
            weeks = int(event.get("weeks", 1))
        return [{"source": "newton3.decay", "weeks": weeks}]

    if "Records" in event:
        for rec in event["Records"]:
            if rec.get("eventSource") == "aws:sqs":
                unwrapped = _unwrap_payload(rec.get("body"))
                if unwrapped:
                    records.append(unwrapped)
            else:
                unwrapped = _unwrap_payload(rec.get("body") or rec.get("detail") or rec)
                if unwrapped:
                    records.append(unwrapped)
        return records

    if "detail" in event:
        unwrapped = _unwrap_payload(event)
        if unwrapped:
            records.append(unwrapped)
        return records

    body = event.get("body")
    if isinstance(body, str):
        body = json.loads(body)
    if isinstance(body, dict):
        records.append(body)
    elif event:
        records.append(event)
    return records


def process_incoming_records(store: ScoreStore, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply behaviour events and weekly decay batches."""
    results: list[dict[str, Any]] = []
    for raw in records:
        if not raw:
            continue
        if raw.get("source") == "newton3.decay" and not raw.get("user_id"):
            weeks = int(raw.get("weeks", 1))
            for prof in store.list_profiles():
                r = process_event(
                    store,
                    BehaviorEvent("weekly_decay", prof.user_id, payload={"weeks": weeks}),
                )
                results.append(_result_dict(r))
            continue
        et = raw.get("event_type") or raw.get("type")
        uid = raw.get("user_id")
        if not et or not uid:
            continue
        if store.get_profile(uid) is None:
            results.append(
                {
                    "user_id": uid,
                    "event_type": et,
                    "applied": False,
                    "detail": "user not registered",
                    "score_after": None,
                    "score_before": None,
                    "score_delta": None,
                    "tier_before": None,
                    "tier_after": None,
                }
            )
            continue
        r = process_event(
            store,
            BehaviorEvent(et, uid, payload=raw.get("payload") or {}),
        )
        results.append(_result_dict(r))
    return results


def _result_dict(r: ProcessResult) -> dict[str, Any]:
    return {
        "user_id": r.user_id,
        "event_type": r.event_type,
        "applied": r.applied,
        "detail": r.detail,
        "score_before": r.score_before,
        "score_after": r.score_after,
        "score_delta": r.score_delta,
        "tier_before": r.tier_before,
        "tier_after": r.tier_after,
    }
