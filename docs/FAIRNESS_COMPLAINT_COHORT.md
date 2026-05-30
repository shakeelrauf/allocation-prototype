# Complaint cohort — fairness validation

Metabase export: **Algorithm User Complaints - Metabase.csv** (not stored in the repo).

## One-step import (UI)

1. Start `python run_local.py --reload --db ./data/newton3.db` and `cd ui && npm run dev`
2. Open **Dashboard** or **Reports**
3. **Select CSV file** — pick your Metabase download
4. Wait for “Imported N users…” — data is in SQLite; use Allocation / Reports next

No `import_fairness_cohort_sheet.py` + `migrate_from_rails_export.py` sequence required.

## One-step import (CLI, optional)

```bash
python scripts/import_fairness_cohort_sheet.py \
  --input "/path/to/Algorithm User Complaints - Metabase.csv" \
  --db ./data/newton3.db
```

## API

```bash
curl -X POST http://127.0.0.1:8765/api/admin/import-users-csv \
  -F "file=@/path/to/Algorithm User Complaints - Metabase.csv"
```

## Column mapping

| Sheet column | Newton use |
|--------------|------------|
| `user_id` | Primary key |
| `user_name` | Display name in UI |
| `group_name` | → `group_id` (slug) + group priority from `team_daily_priority` |
| `individual_priority` / `guaranteed_team` | User priority (guaranteed → 1) |
| `requests_3mo`, `rejection_rate_pct`, `nudge_offences_3mo` | Underserved tier heuristic |
| `Underserved Tier` or `legacy_underserved_tier` | **Legacy** label for comparison |
| `unused_bookings_3mo`, `nudge_offences_3mo` | Synthetic scoring events on import |

## Hackathon narrative

> "We upload the legacy complaint export once, replay no-shows/nudges as behaviour events, and show how Newton ranks high-pain users with good behaviour ahead of sort-only legacy rules — with audit trail and shadow comparison."
