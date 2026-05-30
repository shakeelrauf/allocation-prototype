# Metabase import cache (gitignored)

No CSV data lives in git. **One step in the UI:**

1. Open **Dashboard** or **Reports**
2. **Select CSV file** — choose `Algorithm User Complaints - Metabase.csv`
3. Done — users and events are in SQLite

Optional CLI (same single step):

```bash
python scripts/import_fairness_cohort_sheet.py \
  --input "/path/to/Algorithm User Complaints - Metabase.csv" \
  --db ./data/newton3.db
```

After import, this folder may contain a local cache (ignored by git) for legacy-tier reports.
