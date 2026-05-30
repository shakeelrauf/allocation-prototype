"""WayID-style behaviour score API Lambda."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from newton3.persistence.dynamodb_store import DynamoDBStore
from newton3.domain.models import tier_for_score


def _store() -> DynamoDBStore:
    return DynamoDBStore()


def handler(event, context):
    path = event.get("rawPath") or event.get("path") or ""
    user_id = path.rstrip("/").split("/")[-1]
    if user_id in ("behavior-score", "health"):
        # /users/{id}/behavior-score — id is parent segment
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[-1] == "behavior-score":
            user_id = parts[-2]
        else:
            user_id = ""

    if path.endswith("/health") or path.endswith("/api/health"):
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "status": "ok",
                    "store": "DynamoDBStore",
                    "stack": "aws-sam",
                    "features": {"shadow_mode": True, "tenant_weights": True},
                }
            ),
        }

    store = _store()
    prof = store.get_profile(user_id)
    if prof is None:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"detail": "user not registered"}),
        }
    sc = store.get_score_state(user_id)
    w = store.get_tenant_weights(prof.group_id)
    body = {
        "user_id": user_id,
        "group_id": prof.group_id,
        "score": sc.score,
        "tier": tier_for_score(sc.score).value,
        "last_penalty_at": sc.last_penalty_at.isoformat() if sc.last_penalty_at else None,
        "reward_total_rolling": sc.rolling_reward_total(
            w.reward_cap_window_days, sc.updated_at
        ),
        "updated_at": sc.updated_at.isoformat(),
    }
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
