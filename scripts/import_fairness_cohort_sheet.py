#!/usr/bin/env python3
"""
CLI wrapper — same one-step import as the UI file upload.

  python scripts/import_fairness_cohort_sheet.py \\
    --input "/path/to/Algorithm User Complaints - Metabase.csv" \\
    --db ./data/newton3.db
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from newton3.services.cohort_import import DEFAULT_WORK_DIR, import_metabase_csv_to_store


def main() -> int:
    p = argparse.ArgumentParser(
        description="Import Metabase CSV into Newton (one step — same as UI upload)",
    )
    p.add_argument("--input", type=Path, required=True, help="Metabase CSV or TSV")
    p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (sets NEWTON3_DB_PATH); default: ./data/newton3.db",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_WORK_DIR,
        help="Cache dir for export copy + migration CSVs (gitignored)",
    )
    args = p.parse_args()
    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    if args.db:
        os.environ["NEWTON3_DB_PATH"] = str(args.db.expanduser().resolve())
    elif not os.environ.get("NEWTON3_DB_PATH"):
        from newton3.persistence.sqlite_store import default_sqlite_path

        os.environ["NEWTON3_DB_PATH"] = str(default_sqlite_path().resolve())

    from newton3.persistence.sqlite_store import SqliteStore

    text = args.input.read_text(encoding="utf-8-sig")
    store = SqliteStore(os.environ["NEWTON3_DB_PATH"])
    try:
        result = import_metabase_csv_to_store(
            text,
            store,
            args.output_dir,
            source_name=args.input.name,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    result["sqlite_path"] = str(store._path)
    result["store"] = "SqliteStore"
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
