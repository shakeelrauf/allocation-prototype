"""Fairness analytics — legacy complaint cohort vs Newton tiers."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from typing import Any

from newton3.domain.models import tier_for_score

# Metabase / CS analytics export (CSV or TSV)
FAIRNESS_COHORT_REQUIRED_COLUMNS: tuple[str, ...] = (
    "user_id",
    "user_name",
    "company_name",
    "office_name",
    "group_name",
    "guaranteed_team",
    "team_daily_priority",
    "individual_priority",
    "has_assigned_space",
    "requests_3mo",
    "bookings_3mo",
    "rejected_3mo",
    "unused_bookings_3mo",
    "nudge_offences_3mo",
    "approval_rate_pct",
    "rejection_rate_pct",
    "used_rate_pct",
)

FAIRNESS_COHORT_TIER_COLUMN_ALIASES: tuple[str, ...] = (
    "legacy_underserved_tier",
    "Underserved Tier",
)

FAIRNESS_COHORT_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".tsv", ".txt"})

MAX_COHORT_UPLOAD_BYTES = 15 * 1024 * 1024


def _normalize_header(name: str) -> str:
    return re.sub(r"\s+", "_", (name or "").strip().lower())


def read_fairness_cohort_table(text: str) -> tuple[list[dict[str, str]], str]:
    """Parse complaint-cohort export text; returns rows and delimiter."""
    if not text or not text.strip():
        return [], ","
    sample = text.lstrip("\ufeff")
    first = next((ln for ln in sample.splitlines() if ln.strip()), "")
    delim = "\t" if "\t" in first else ","
    rows = list(csv.DictReader(io.StringIO(sample), delimiter=delim))
    return rows, delim


def validate_fairness_cohort_text(
    text: str,
    *,
    filename: str | None = None,
) -> dict[str, Any]:
    """
    Validate uploaded complaint-cohort CSV/TSV before import.

    Returns a dict with ``ok``, ``errors``, ``warnings``, and row/column stats.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext and ext not in FAIRNESS_COHORT_ALLOWED_EXTENSIONS:
            errors.append(
                f"Unsupported file type '{ext}'. Use CSV or TSV ({', '.join(sorted(FAIRNESS_COHORT_ALLOWED_EXTENSIONS))})."
            )

    if not text or not text.strip():
        errors.append("File is empty.")
        return _validation_result(errors, warnings, rows=[], delim=",")

    if len(text.encode("utf-8")) > MAX_COHORT_UPLOAD_BYTES:
        errors.append(f"File exceeds {MAX_COHORT_UPLOAD_BYTES // (1024 * 1024)} MB limit.")

    raw, delim = read_fairness_cohort_table(text)
    if not raw:
        errors.append("No data rows found (header only or unreadable table).")
        return _validation_result(errors, warnings, rows=raw, delim=delim)

    fieldnames = list(raw[0].keys())
    if not fieldnames or all(not (h or "").strip() for h in fieldnames):
        errors.append("Missing or empty header row.")
        return _validation_result(errors, warnings, rows=raw, delim=delim)

    norm_headers = {_normalize_header(h) for h in fieldnames if h}
    missing: list[str] = []
    for col in FAIRNESS_COHORT_REQUIRED_COLUMNS:
        if _normalize_header(col) not in norm_headers:
            missing.append(col)
    tier_ok = any(_normalize_header(t) in norm_headers for t in FAIRNESS_COHORT_TIER_COLUMN_ALIASES)
    if not tier_ok:
        missing.append("legacy_underserved_tier (or Underserved Tier)")

    if missing:
        errors.append(
            "Missing required columns: " + ", ".join(missing) + ". "
            "Expected a Metabase-style complaint cohort export."
        )

    valid = 0
    skipped = 0
    for row in raw:
        if FairnessCohortRow.from_csv_dict(row) is None:
            skipped += 1
        else:
            valid += 1

    if valid == 0 and not errors:
        errors.append(
            "No importable rows — every row is missing user_id or failed parsing."
        )
    elif skipped > 0:
        warnings.append(f"{skipped} row(s) skipped (missing user_id or invalid).")

    if valid > 0 and skipped / max(valid + skipped, 1) > 0.5:
        warnings.append("More than half of data rows were skipped — check column alignment.")

    return _validation_result(errors, warnings, rows=raw, delim=delim, valid=valid, skipped=skipped)


def _validation_result(
    errors: list[str],
    warnings: list[str],
    *,
    rows: list[dict[str, str]],
    delim: str,
    valid: int | None = None,
    skipped: int | None = None,
) -> dict[str, Any]:
    if valid is None:
        valid = 0
        skipped = 0
        for row in rows:
            if FairnessCohortRow.from_csv_dict(row) is None:
                skipped += 1
            else:
                valid += 1
    data_rows = len(rows)
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "delimiter": delim,
        "data_rows": data_rows,
        "valid_rows": valid,
        "skipped_rows": skipped or 0,
        "required_columns": list(FAIRNESS_COHORT_REQUIRED_COLUMNS),
        "tier_columns": list(FAIRNESS_COHORT_TIER_COLUMN_ALIASES),
    }


def derive_underserved_tier(
    *,
    requests: int,
    rejection_rate_pct: float,
    nudge_offences: int,
) -> str:
    """
    Heuristic underserved tier aligned with legacy complaint-cohort labelling.

    Z = no/low activity, C–A = rising need, M/X = high pain, P = protected/guaranteed.
    """
    if requests <= 0:
        return "Z"
    if nudge_offences >= 3 or rejection_rate_pct >= 80:
        return "X"
    if rejection_rate_pct >= 60:
        return "M"
    if requests >= 40 and rejection_rate_pct >= 25:
        return "A"
    if requests >= 15:
        return "B"
    return "C"


def parse_team_daily_priority(raw: str | None) -> int:
    """
    Legacy sheet stores per-weekday priorities as JSON, e.g.
    ``["", "4", "4", "9", "4", "4", ""]`` — use the best (minimum) numeric slot.
    """
    if not raw or not str(raw).strip():
        return 100
    s = str(raw).strip()
    try:
        arr = json.loads(s.replace("'", '"'))
    except json.JSONDecodeError:
        nums = [int(x) for x in re.findall(r"\d+", s)]
        return min(nums) if nums else 100
    nums: list[int] = []
    for x in arr:
        if x is None or x == "":
            continue
        try:
            nums.append(int(x))
        except (TypeError, ValueError):
            continue
    return min(nums) if nums else 100


def parse_individual_priority(raw: str | None, *, guaranteed_team: bool) -> int:
    if guaranteed_team:
        return 1
    if raw is None or not str(raw).strip():
        return 100
    try:
        return int(str(raw).strip())
    except ValueError:
        return 100


def slug_group_id(group_name: str) -> str:
    g = (group_name or "default").strip().lower()
    g = re.sub(r"[^a-z0-9]+", "-", g).strip("-")
    return (g[:80] or "default") if g else "default"


@dataclass
class FairnessCohortRow:
    user_id: str
    user_name: str
    company_name: str
    office_name: str
    group_name: str
    guaranteed_team: bool
    team_daily_priority: str
    individual_priority: str
    has_assigned_space: bool
    requests_3mo: int
    bookings_3mo: int
    rejected_3mo: int
    unused_bookings_3mo: int
    nudge_offences_3mo: int
    approval_rate_pct: float
    rejection_rate_pct: float
    used_rate_pct: float
    legacy_underserved_tier: str

    @classmethod
    def from_csv_dict(cls, row: dict[str, str]) -> FairnessCohortRow | None:
        uid = (row.get("user_id") or "").strip()
        if not uid:
            return None
        gt = (row.get("guaranteed_team") or "").strip().upper() in ("TRUE", "1", "YES")
        def _int(k: str) -> int:
            try:
                return int(float((row.get(k) or "0").strip() or "0"))
            except ValueError:
                return 0

        def _float(k: str) -> float:
            try:
                return float((row.get(k) or "0").strip() or "0")
            except ValueError:
                return 0.0

        legacy = (row.get("legacy_underserved_tier") or row.get("Underserved Tier") or "").strip()
        return cls(
            user_id=uid,
            user_name=(row.get("user_name") or "").strip(),
            company_name=(row.get("company_name") or "").strip(),
            office_name=(row.get("office_name") or "").strip(),
            group_name=(row.get("group_name") or "default").strip(),
            guaranteed_team=gt,
            team_daily_priority=(row.get("team_daily_priority") or "").strip(),
            individual_priority=(row.get("individual_priority") or "").strip(),
            has_assigned_space=(row.get("has_assigned_space") or "").strip().lower()
            in ("yes", "true", "1"),
            requests_3mo=_int("requests_3mo"),
            bookings_3mo=_int("bookings_3mo"),
            rejected_3mo=_int("rejected_3mo"),
            unused_bookings_3mo=_int("unused_bookings_3mo"),
            nudge_offences_3mo=_int("nudge_offences_3mo"),
            approval_rate_pct=_float("approval_rate_pct"),
            rejection_rate_pct=_float("rejection_rate_pct"),
            used_rate_pct=_float("used_rate_pct"),
            legacy_underserved_tier=legacy or "Z",
        )

    def computed_underserved_tier(self) -> str:
        return derive_underserved_tier(
            requests=self.requests_3mo,
            rejection_rate_pct=self.rejection_rate_pct,
            nudge_offences=self.nudge_offences_3mo,
        )

    def group_priority(self) -> int:
        return parse_team_daily_priority(self.team_daily_priority)

    def user_priority(self) -> int:
        return parse_individual_priority(
            self.individual_priority, guaranteed_team=self.guaranteed_team
        )


def cohort_analysis_row(
    row: FairnessCohortRow,
    *,
    behavior_score: float,
    newton_rank: int | None = None,
    pool_size: int | None = None,
) -> dict[str, Any]:
    """One comparison line for API/UI."""
    legacy = row.legacy_underserved_tier or "Z"
    computed = row.computed_underserved_tier()
    btier = tier_for_score(behavior_score).value
    high_pain = legacy in ("X", "M", "A") or row.rejection_rate_pct >= 40
    newton_helps = high_pain and behavior_score >= 80
    return {
        "user_id": row.user_id,
        "user_name": row.user_name,
        "company_name": row.company_name,
        "group_name": row.group_name,
        "requests_3mo": row.requests_3mo,
        "rejection_rate_pct": row.rejection_rate_pct,
        "unused_bookings_3mo": row.unused_bookings_3mo,
        "nudge_offences_3mo": row.nudge_offences_3mo,
        "legacy_underserved_tier": legacy,
        "computed_underserved_tier": computed,
        "legacy_tier_matches_computed": legacy == computed,
        "behavior_score": round(behavior_score, 2),
        "behavior_tier": btier,
        "newton_rank": newton_rank,
        "pool_size": pool_size,
        "high_pain_legacy": high_pain,
        "newton_behavior_helps_eligibility": newton_helps,
    }


def cohort_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"users": 0}
    legacy_mx = sum(1 for r in rows if r.get("legacy_underserved_tier") in ("M", "X"))
    helps = sum(1 for r in rows if r.get("newton_behavior_helps_eligibility"))
    match = sum(1 for r in rows if r.get("legacy_tier_matches_computed"))
    return {
        "users": len(rows),
        "legacy_high_pain_mx": legacy_mx,
        "newton_would_help_count": helps,
        "computed_tier_matches_legacy": match,
        "computed_tier_match_pct": round(100.0 * match / len(rows), 1),
        "avg_rejection_rate_pct": round(
            sum(float(r.get("rejection_rate_pct") or 0) for r in rows) / len(rows), 1
        ),
        "avg_behavior_score": round(
            sum(float(r.get("behavior_score") or 0) for r in rows) / len(rows), 1
        ),
    }
