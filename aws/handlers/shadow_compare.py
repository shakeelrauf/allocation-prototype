"""Shadow validation job — compare Newton AWS ranking vs legacy reference JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from newton3.domain.allocation_engine import rank_users
from newton3.persistence.dynamodb_store import DynamoDBStore
from newton3.domain.shadow_engine import rank_legacy, shadow_diff


def handler(event, context):
    """
    Input (EventBridge or direct invoke):
    {
      "user_ids": ["a","b","c"],
      "seed": 1,
      "legacy_ranks": [{"user_id":"a","rank":1}, ...]  // optional Rails export
    }
    """
    store = DynamoDBStore()
    user_ids = event.get("user_ids") or []
    seed = event.get("seed")
    newton = rank_users(store, user_ids, seed=seed)
    legacy_local = rank_legacy(store, user_ids, seed=seed)

    legacy_ref = event.get("legacy_ranks")
    mismatches = []
    if legacy_ref:
        ref_pos = {r["user_id"]: r["rank"] for r in legacy_ref}
        for r in newton:
            ref_rank = ref_pos.get(r.user_id)
            if ref_rank is not None and ref_rank != r.rank:
                mismatches.append(
                    {
                        "user_id": r.user_id,
                        "newton_rank": r.rank,
                        "legacy_rank": ref_rank,
                    }
                )

    diff = shadow_diff(newton, legacy_local)
    ok = len(mismatches) == 0
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "parity_ok": ok,
                "mismatch_count": len(mismatches),
                "mismatches_vs_rails_export": mismatches,
                "newton_vs_local_legacy_diff": diff,
            }
        ),
    }
