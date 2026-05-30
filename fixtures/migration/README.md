# Migration CSVs (not in git)

Place your own `groups.csv`, `users.csv`, and optional `events.csv` here for:

```bash
python scripts/migrate_from_rails_export.py --dir fixtures/migration --dry-run
```

Or import the Metabase export from the UI / `import_fairness_cohort_sheet.py`, which populates `fixtures/complaint_cohort/generated/` instead.
