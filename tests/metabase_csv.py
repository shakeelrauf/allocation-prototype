"""Inline Metabase-style CSV for tests (no committed data files in the repo)."""

from __future__ import annotations

METABASE_HEADER = (
    "user_id,user_name,company_name,office_name,group_name,guaranteed_team,"
    "team_daily_priority,individual_priority,has_assigned_space,requests_3mo,"
    "bookings_3mo,rejected_3mo,unused_bookings_3mo,nudge_offences_3mo,"
    "approval_rate_pct,rejection_rate_pct,used_rate_pct,company_id,office_id,"
    "legacy_underserved_tier"
)

METABASE_HEADER_UNDERSERVED_ALIAS = METABASE_HEADER.replace(
    "legacy_underserved_tier", "Underserved Tier"
)


def metabase_csv_row(
    user_id: str,
    *,
    user_name: str = "Test User",
    company_name: str = "Acme",
    office_name: str = "HQ",
    group_name: str = "Parking Pool",
    tier: str = "Z",
    requests: int = 5,
    rejected: int = 0,
) -> str:
    return (
        f"{user_id},{user_name},{company_name},{office_name},{group_name},FALSE,"
        f'"[]",,No,{requests},0,{rejected},0,0,0,0,0,,,{tier}'
    )


def minimal_metabase_csv(*, rows: int = 25, tier: str = "Z") -> str:
    lines = [METABASE_HEADER]
    for i in range(rows):
        uid = str(9000 + i)
        lines.append(
            metabase_csv_row(
                uid,
                user_name=f"User {i}",
                company_name="GCU" if i % 5 == 0 else "Acme",
                tier=tier if i > 0 else "A",
                requests=10 + i,
                rejected=2 if i % 3 == 0 else 0,
            )
        )
    return "\n".join(lines) + "\n"
