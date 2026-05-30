"""Newton allocation Lambda — rank / allocate / shadow."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from newton3.domain.allocation_engine import allocate_spaces, allocation_explain_for_user, rank_users
from newton3.persistence.dynamodb_store import DynamoDBStore
from newton3.domain.models import tier_for_score
from newton3.domain.shadow_engine import rank_legacy, shadow_diff


def _store() -> DynamoDBStore:
    return DynamoDBStore()


def _qs(event) -> dict[str, str]:
    params = event.get("queryStringParameters") or {}
    if params:
        return {k: str(v) for k, v in params.items()}
    raw = event.get("rawQueryString") or ""
    parsed = parse_qs(raw, keep_blank_values=True)
    return {k: (v[0] if v else "") for k, v in parsed.items()}


def handler(event, context):
    store = _store()
    path = (event.get("rawPath") or event.get("path") or "").rstrip("/")
    method = event.get("requestContext", {}).get("http", {}).get("method") or event.get(
        "httpMethod", "GET"
    )
    q = _qs(event)

    if path.endswith("/rank") or path.endswith("/allocation/rank"):
        ids = [x.strip() for x in q.get("user_ids", "").split(",") if x.strip()]
        seed = int(q["seed"]) if q.get("seed") else None
        rows = rank_users(store, ids, seed=seed)
        body = {
            "ranking": [
                {"rank": r.rank, "user_id": r.user_id, "explain": r.explain} for r in rows
            ]
        }
    elif path.endswith("/allocate") or path.endswith("/allocation/allocate"):
        ids = [x.strip() for x in q.get("user_ids", "").split(",") if x.strip()]
        cap = int(q.get("capacity", "0"))
        seed = int(q["seed"]) if q.get("seed") else None
        rows = allocate_spaces(store, ids, capacity=cap, seed=seed)
        aid = store.record_space_allocation(ids, cap, seed, rows)
        body = {
            "allocation_id": aid,
            "capacity": cap,
            "winners": [
                {
                    "rank": r.rank,
                    "user_id": r.user_id,
                    "explain": r.explain,
                    "behavior_score": store.get_score_state(r.user_id).score,
                    "tier": tier_for_score(store.get_score_state(r.user_id).score).value,
                }
                for r in rows
            ],
        }
    elif path.endswith("/shadow") or path.endswith("/allocation/shadow"):
        ids = [x.strip() for x in q.get("user_ids", "").split(",") if x.strip()]
        seed = int(q["seed"]) if q.get("seed") else None
        newton = rank_users(store, ids, seed=seed)
        legacy = rank_legacy(store, ids, seed=seed)
        body = {
            "newton": [
                {"rank": r.rank, "user_id": r.user_id, "explain": r.explain} for r in newton
            ],
            "legacy_mock": [
                {"rank": r.rank, "user_id": r.user_id, "explain": r.explain} for r in legacy
            ],
            "diff": shadow_diff(newton, legacy),
        }
    elif path.endswith("/explain") or path.endswith("/allocation/explain"):
        ids = [x.strip() for x in q.get("user_ids", "").split(",") if x.strip()]
        focus = q.get("focus", "")
        seed = int(q["seed"]) if q.get("seed") else None
        body = allocation_explain_for_user(store, ids, focus, seed=seed)
    else:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "unknown allocation route", "path": path}),
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
