from tests.metabase_csv import (
    METABASE_HEADER_UNDERSERVED_ALIAS,
    minimal_metabase_csv,
    metabase_csv_row,
)
from newton3.domain.fairness import (
    FairnessCohortRow,
    derive_underserved_tier,
    parse_team_daily_priority,
    slug_group_id,
    validate_fairness_cohort_text,
)


def test_derive_underserved_tier_examples():
    assert derive_underserved_tier(requests=0, rejection_rate_pct=0, nudge_offences=0) == "Z"
    assert derive_underserved_tier(requests=41, rejection_rate_pct=30, nudge_offences=0) == "A"
    assert derive_underserved_tier(requests=10, rejection_rate_pct=85, nudge_offences=0) == "X"
    assert derive_underserved_tier(requests=5, rejection_rate_pct=50, nudge_offences=3) == "X"


def test_parse_team_daily_priority_json():
    raw = '["", "4", "9", "4", "4", "4", ""]'
    assert parse_team_daily_priority(raw) == 4


def test_inline_metabase_csv_parses():
    text = minimal_metabase_csv(rows=25)
    rows = []
    import csv
    import io

    for raw in csv.DictReader(io.StringIO(text)):
        r = FairnessCohortRow.from_csv_dict(raw)
        if r:
            rows.append(r)
    assert len(rows) >= 20
    gcu = [r for r in rows if "GCU" in r.company_name or r.company_name == "Acme"]
    assert gcu


def test_slug_group_id():
    assert slug_group_id("B2 and B3 Parking") == "b2-and-b3-parking"


def test_validate_sample_csv_ok():
    text = minimal_metabase_csv(rows=25)
    v = validate_fairness_cohort_text(text, filename="metabase.csv")
    assert v["ok"] is True
    assert v["valid_rows"] >= 20
    assert v["errors"] == []


def test_validate_rejects_missing_columns():
    v = validate_fairness_cohort_text("user_id,name\n1,Alice\n", filename="bad.csv")
    assert v["ok"] is False
    assert any("Missing required columns" in e for e in v["errors"])


def test_validate_rejects_wrong_extension():
    v = validate_fairness_cohort_text("user_id\n1\n", filename="export.xlsx")
    assert v["ok"] is False
    assert any("Unsupported file type" in e for e in v["errors"])


def test_validate_accepts_underserved_tier_alias():
    row = metabase_csv_row("99", tier="Z")
    text = METABASE_HEADER_UNDERSERVED_ALIAS + "\n" + row
    v = validate_fairness_cohort_text(text, filename="metabase.csv")
    assert v["ok"] is True
