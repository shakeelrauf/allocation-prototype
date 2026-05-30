"""SQS / EventBridge schedule → scoring worker. Reuses ``events_queue`` + ``event_processor``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from newton3.persistence.dynamodb_store import DynamoDBStore
from newton3.services.events_queue import collect_incoming_records, process_incoming_records


def _store() -> DynamoDBStore:
    return DynamoDBStore()


def handler(event, context):
    store = _store()
    records = collect_incoming_records(event)
    results = process_incoming_records(store, records)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"count": len(results), "results": results}),
    }
