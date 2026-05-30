"""
One-step Metabase CSV import: validate → transform → load into ScoreStore.

Used by the API (browser file upload) and optional CLI wrapper in ``scripts/``.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from newton3.domain.fairness import (
    FairnessCohortRow,
    read_fairness_cohort_table,
    slug_group_id,
    validate_fairness_cohort_text,
)
from newton3.domain.models import EventType
from scripts.migrate_from_rails_export import run_migration
from newton3.persistence.store import ScoreStore

from newton3.paths import REPO_ROOT

DEFAULT_WORK_DIR = REPO_ROOT / "fixtures" / "complaint_cohort" / "generated"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build_from_sheet(rows: list[dict[str, str]]) -> tuple[list[FairnessCohortRow], dict]:
    parsed: list[FairnessCohortRow] = []
    skipped = 0
    for raw in rows:
        row = FairnessCohortRow.from_csv_dict(raw)
        if row is None:
            skipped += 1
            continue
        parsed.append(row)
    return parsed, {"skipped": skipped, "imported": len(parsed)}


def emit_migration_files(
    cohort: list[FairnessCohortRow],
    out_dir: Path,
    *,
    max_events_per_user: int = 8,
) -> dict:
    group_pri: dict[str, int] = {}
    users_out: list[dict] = []
    events_out: list[dict] = []

    for row in cohort:
        gid = slug_group_id(row.group_name)
        gp = row.group_priority()
        group_pri[gid] = min(group_pri.get(gid, gp), gp)
        users_out.append(
            {
                "user_id": row.user_id,
                "user_name": row.user_name,
                "group_id": gid,
                "group_priority": gp,
                "user_priority": row.user_priority(),
            }
        )
        unused = min(row.unused_bookings_3mo, max_events_per_user)
        for _ in range(unused):
            events_out.append(
                {
                    "event_type": EventType.UNUSED_BOOKING.value,
                    "user_id": row.user_id,
                    "timestamp": "",
                    "payload_json": "{}",
                }
            )
        nudge = min(row.nudge_offences_3mo, max_events_per_user)
        for _ in range(nudge):
            events_out.append(
                {
                    "event_type": EventType.OFFENCE_REPORTED.value,
                    "user_id": row.user_id,
                    "timestamp": "",
                    "payload_json": "{}",
                }
            )

    groups_out = [
        {"group_id": gid, "group_priority": pri} for gid, pri in sorted(group_pri.items())
    ]

    audit = [
        {
            "user_id": r.user_id,
            "user_name": r.user_name,
            "legacy_underserved_tier": r.legacy_underserved_tier,
            "computed_underserved_tier": r.computed_underserved_tier(),
            "rejection_rate_pct": r.rejection_rate_pct,
            "requests_3mo": r.requests_3mo,
        }
        for r in cohort
    ]

    _write_csv(
        out_dir / "users.csv",
        ["user_id", "user_name", "group_id", "group_priority", "user_priority"],
        users_out,
    )
    _write_csv(out_dir / "groups.csv", ["group_id", "group_priority"], groups_out)
    _write_csv(
        out_dir / "events.csv",
        ["event_type", "user_id", "timestamp", "payload_json"],
        events_out,
    )
    (out_dir / "fairness_cohort.json").write_text(
        json.dumps({"rows": audit}, indent=2), encoding="utf-8"
    )
    export_copy = out_dir / "fairness_cohort_export.csv"
    return {
        "users": len(users_out),
        "groups": len(groups_out),
        "events": len(events_out),
        "output_dir": str(out_dir),
        "cohort_csv": str(export_copy),
    }


def prepare_metabase_csv(text: str, work_dir: Path, *, source_name: str = "upload.csv") -> dict[str, Any]:
    """Validate Metabase export and write migration-shaped files under *work_dir*."""
    validation = validate_fairness_cohort_text(text, filename=source_name)
    if not validation["ok"]:
        raise ValueError(json.dumps(validation))

    rows, _ = read_fairness_cohort_table(text)
    cohort, meta = build_from_sheet(rows)
    if not cohort:
        raise ValueError("No rows imported after validation")

    stats = emit_migration_files(cohort, work_dir)
    (work_dir / "fairness_cohort_export.csv").write_text(text, encoding="utf-8")
    return {
        "meta": meta,
        "validation": validation,
        "import_stats": stats,
        "cohort_csv": str(work_dir / "fairness_cohort_export.csv"),
    }


def load_prepared_csv_into_store(store: ScoreStore, work_dir: Path) -> Any:
    """Clear store (if supported) and replay users/groups/events from *work_dir*."""
    clear_fn = getattr(store, "clear_all_data", None)
    if callable(clear_fn):
        clear_fn()
    return run_migration(store, work_dir, replay_events=True)


def import_metabase_csv_to_store(
    text: str,
    store: ScoreStore,
    work_dir: Path | None = None,
    *,
    source_name: str = "upload.csv",
) -> dict[str, Any]:
    """
    Single entry point: raw Metabase CSV text → SQLite (or any ScoreStore).

    No separate migrate script step required.
    """
    out = work_dir or DEFAULT_WORK_DIR
    prepared = prepare_metabase_csv(text, out, source_name=source_name)
    audit = load_prepared_csv_into_store(store, out)
    return {
        "ok": True,
        "source": "upload",
        "validation": prepared["validation"],
        "import_stats": prepared["import_stats"],
        "meta": prepared["meta"],
        "migration_audit": audit.__dict__,
        "cohort_csv": prepared["cohort_csv"],
        "users_in_db": len(store.list_profiles()),
    }
