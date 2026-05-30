"""FastAPI service + static UI. Uses SQLite via SqliteStore unless a store is injected."""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from datetime import timedelta
from typing import Any, Literal

try:
    from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field, field_validator
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "Install API deps: pip install -e '.[api]' "
        "or pip install -r requirements-dev.txt"
    ) from e

from newton3.domain.allocation_engine import (
    allocate_spaces,
    allocation_explain_for_user,
    build_allocation_outcome,
    rank_users,
)
from newton3.domain.event_processor import process_event, seed_users
from newton3.domain.insights import ensemble_anomaly_flags, no_show_risk, score_anomaly
from newton3.services.llm_explain import enrich_with_llm, gather_llm_store_snapshot, llm_feature_flags
from newton3.domain.models import BehaviorEvent, UserProfile, tier_for_score
from newton3.domain.shadow_engine import rank_legacy, shadow_diff
from newton3.services.events_queue import enqueue_behavior_event, events_async_enabled, should_enqueue_http_event
from newton3.persistence.store import ScoreStore
from newton3.persistence.store_factory import admin_enabled, make_store, store_kind
from newton3.domain.tenant_weights import TenantWeights
from newton3.domain.fairness import (
    MAX_COHORT_UPLOAD_BYTES,
    FairnessCohortRow,
    cohort_analysis_row,
    cohort_summary,
    derive_underserved_tier,
    validate_fairness_cohort_text,
)
from newton3.paths import REPO_ROOT


def _fairness_cohort_csv_path() -> Path | None:
    """Last uploaded Metabase export (written on import). No bundled sample CSV in repo."""
    raw = os.environ.get("NEWTON3_FAIRNESS_COHORT_CSV")
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_file() else None
    generated = REPO_ROOT / "fixtures" / "complaint_cohort" / "generated" / "fairness_cohort_export.csv"
    return generated if generated.is_file() else None


def _default_fairness_cohort_json() -> Path:
    return REPO_ROOT / "fixtures" / "complaint_cohort" / "generated" / "fairness_cohort.json"


def _load_fairness_cohort_index() -> dict[str, dict]:
    """Legacy underserved labels from complaint-cohort export (by user_id)."""
    raw_path = os.environ.get("NEWTON3_FAIRNESS_COHORT_JSON")
    path = Path(raw_path).expanduser() if raw_path else _default_fairness_cohort_json()
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return {}
    return {str(r.get("user_id")): r for r in rows if r.get("user_id")}


def _user_name_index() -> dict[str, str]:
    """Map user_id → display name from complaint-cohort export (CSV + JSON)."""
    names: dict[str, str] = {}
    csv_path = _fairness_cohort_csv_path()
    if csv_path is not None:
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                uid = (row.get("user_id") or "").strip()
                uname = (row.get("user_name") or "").strip()
                if uid and uname:
                    names[uid] = uname
    for uid, row in _load_fairness_cohort_index().items():
        if isinstance(row, dict):
            uname = (row.get("user_name") or "").strip()
            if uid and uname:
                names[uid] = uname
    return names


def _user_name_for(user_id: str, names: dict[str, str] | None = None) -> str:
    if names is None:
        names = _user_name_index()
    return names.get(user_id, "")


def _enrich_user_row(row: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    uid = str(row.get("user_id", "") or "")
    if not uid:
        return row
    out = dict(row)
    out["user_name"] = _user_name_for(uid, names)
    return out


def _enrich_allocation_runs(runs: list[dict[str, Any]], names: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for run in runs:
        r = dict(run)
        r["winners"] = [_enrich_user_row(w, names) for w in r.get("winners", [])]
        out.append(r)
    return out


def _enrich_explain_payload(payload: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    out = dict(payload)
    fid = str(out.get("focus_user_id", "") or "")
    if fid:
        out["focus_user_name"] = _user_name_for(fid, names)
    for key in ("users_above", "why_above"):
        if isinstance(out.get(key), list):
            out[key] = [_enrich_user_row(r, names) for r in out[key]]
    if isinstance(out.get("ranking"), list):
        out["ranking"] = [_enrich_user_row(r, names) for r in out["ranking"]]
    fd = out.get("focus_detail")
    if isinstance(fd, dict) and fid:
        fd = dict(fd)
        fd["user_name"] = _user_name_for(fid, names)
        out["focus_detail"] = fd
    return out


class UserIn(BaseModel):
    user_id: str
    group_id: str = "default"
    group_priority: int = 100
    user_priority: int = 100


class GroupIn(BaseModel):
    group_id: str
    group_priority: int = 100


class EventIn(BaseModel):
    event_type: str
    user_id: str
    payload: dict = Field(default_factory=dict)


class TenantConfigIn(BaseModel):
    group_id: str
    weights: dict[str, Any] = Field(default_factory=dict)


class LlmChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=12000)

    @field_validator("content")
    @classmethod
    def strip_nonempty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("content cannot be empty")
        return s


class LlmExplainIn(BaseModel):
    user_ids: str
    seed: int | None = None
    context: str = ""
    messages: list[LlmChatMessage] = Field(default_factory=list)
    follow_up: str | None = Field(None, max_length=12000)
    allocation_capacity: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Winners shown in the LLM snapshot block (defaults from NEWTON3_LLM_ALLOC_CAPACITY).",
    )

    @field_validator("messages", mode="after")
    @classmethod
    def cap_history(cls, v: list[LlmChatMessage]) -> list[LlmChatMessage]:
        return v[-48:] if len(v) > 48 else v


class BulkEventsIn(BaseModel):
    events: list[EventIn]


def _make_default_store() -> ScoreStore:
    return make_store()


def _require_admin() -> None:
    if not admin_enabled():
        raise HTTPException(403, "admin API disabled in this environment")


def _store_sqlite_path(store: ScoreStore) -> str | None:
    dbp = getattr(store, "_path", None)
    return str(dbp) if dbp else None


def _behavior_score_payload(st: ScoreStore, user_id: str) -> dict[str, Any]:
    prof = st.get_profile(user_id)
    if prof is None:
        raise HTTPException(404, "user not registered")
    sc = st.get_score_state(user_id)
    names = _user_name_index()
    return {
        "user_id": user_id,
        "user_name": _user_name_for(user_id, names),
        "group_id": prof.group_id,
        "score": sc.score,
        "tier": tier_for_score(sc.score).value,
        "last_penalty_at": sc.last_penalty_at.isoformat() if sc.last_penalty_at else None,
        "reward_total_rolling": sc.rolling_reward_total(28, sc.updated_at),
        "updated_at": sc.updated_at.isoformat(),
    }


def create_app(store: ScoreStore | None = None) -> FastAPI:
    """Wire routes and optional static UI. Default persistence is SQLite on disk."""
    app = FastAPI(title="Newton 3.0 — behaviour scoring", version="0.3.0")
    app.state.store = store if store is not None else _make_default_store()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("NEWTON3_CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def st() -> ScoreStore:
        return app.state.store

    @app.get("/api/health")
    def health():
        llm_flags = llm_feature_flags()
        store = app.state.store
        body: dict[str, Any] = {
            "status": "ok",
            "store": type(store).__name__,
            "store_backend": store_kind(),
            "stack": os.environ.get("NEWTON3_STACK", "local"),
            "features": {
                "shadow_mode": True,
                "score_history": hasattr(store, "list_score_history"),
                "tenant_weights": hasattr(store, "set_tenant_weights"),
                "groups_registry": hasattr(store, "list_groups"),
                "llm_explain_env": llm_flags["llm_explain_env"],
                "llm_backend": llm_flags["llm_backend"],
                "llm_auto_ollama": llm_flags["llm_auto_ollama"],
                "llm_character": llm_flags["llm_character"],
                "events_async": events_async_enabled(),
                "admin_api": admin_enabled(),
            },
        }
        if type(store).__name__ == "SqliteStore":
            dbp = getattr(store, "_path", None)
            if dbp:
                body["sqlite_path"] = str(dbp)
        return body

    @app.get("/users/{user_id}/behavior-score", tags=["spec-alias"])
    def behavior_score_spec_path(user_id: str):
        """Spec-style path (no /api prefix) for judges reading OpenAPI."""
        return _behavior_score_payload(st(), user_id)

    @app.get("/api/users")
    def list_users():
        s = st()
        names = _user_name_index()
        rows = []
        for prof in s.list_profiles():
            sc = s.get_score_state(prof.user_id)
            rows.append(
                {
                    "user_id": prof.user_id,
                    "user_name": (prof.user_name or "").strip()
                    or _user_name_for(prof.user_id, names),
                    "group_id": prof.group_id,
                    "group_priority": prof.group_priority,
                    "user_priority": prof.user_priority,
                    "score": sc.score,
                    "tier": tier_for_score(sc.score).value,
                    "last_penalty_at": sc.last_penalty_at.isoformat()
                    if sc.last_penalty_at
                    else None,
                    "reward_total_rolling": sc.rolling_reward_total(28, sc.updated_at),
                    "updated_at": sc.updated_at.isoformat(),
                }
            )
        return {"users": rows}

    @app.get("/api/groups")
    def list_groups_api():
        fn = getattr(st(), "list_groups", None)
        if not callable(fn):
            return {"groups": []}
        return {"groups": fn()}

    @app.post("/api/admin/reset")
    def admin_reset_all_data():
        """Clear all persisted demo data (SQLite or in-memory)."""
        _require_admin()
        fn = getattr(st(), "clear_all_data", None)
        if not callable(fn):
            raise HTTPException(501, "this store does not support reset")
        fn()
        return {"ok": True}

    @app.post("/api/admin/groups")
    def admin_create_group(body: GroupIn):
        _require_admin()
        fn = getattr(st(), "ensure_group", None)
        if not callable(fn):
            raise HTTPException(501, "this store does not support groups registry")
        gid = body.group_id.strip()
        if not gid:
            raise HTTPException(400, "group_id required")
        fn(gid, body.group_priority)
        return {"ok": True, "group_id": gid, "group_priority": body.group_priority}

    @app.post("/api/admin/users")
    def register_users(users: list[UserIn]):
        _require_admin()
        s = st()
        lg_fn = getattr(s, "list_groups", None)
        eg_fn = getattr(s, "ensure_group", None)
        known: dict[str, int] = {}
        if callable(lg_fn):
            known = {g["group_id"]: g["group_priority"] for g in lg_fn()}
        profs: list[UserProfile] = []
        for u in users:
            gid = u.group_id.strip() or "default"
            if gid in known:
                gp = known[gid]
            else:
                gp = u.group_priority
                if callable(eg_fn):
                    eg_fn(gid, gp)
                    known[gid] = gp
            profs.append(
                UserProfile(u.user_id.strip(), gid, group_priority=gp, user_priority=u.user_priority)
            )
        seed_users(s, profs)
        return {"ok": True, "count": len(users)}

    @app.post("/api/admin/tenant-config")
    def put_tenant_config(body: TenantConfigIn):
        _require_admin()
        fn = getattr(st(), "set_tenant_weights", None)
        if not callable(fn):
            raise HTTPException(501, "this store does not support tenant config")
        w = TenantWeights.from_dict(body.weights) if body.weights else TenantWeights.default()
        fn(body.group_id, w)
        return {"ok": True, "group_id": body.group_id, "weights": w.to_dict()}

    @app.get("/api/admin/tenant-config/{group_id}")
    def get_tenant_config(group_id: str):
        fn = getattr(st(), "get_tenant_weights", None)
        if not callable(fn):
            raise HTTPException(501, "this store does not support tenant config")
        w = fn(group_id)
        return {"group_id": group_id, "weights": w.to_dict()}

    @app.post("/api/events")
    def ingest_event(body: EventIn):
        if should_enqueue_http_event():
            meta = enqueue_behavior_event(body.event_type, body.user_id, body.payload)
            return Response(
                content=json.dumps(
                    {
                        "queued": True,
                        "message_id": meta.get("message_id"),
                        "detail": "Event queued for scoring worker",
                        "event_type": body.event_type,
                        "user_id": body.user_id,
                    }
                ),
                status_code=202,
                media_type="application/json",
            )
        r = process_event(
            st(),
            BehaviorEvent(body.event_type, body.user_id, payload=body.payload),
        )
        return {
            "applied": r.applied,
            "detail": r.detail,
            "score_before": r.score_before,
            "score_after": r.score_after,
            "score_delta": r.score_delta,
            "tier_before": r.tier_before,
            "tier_after": r.tier_after,
        }

    @app.post("/api/events/bulk")
    def ingest_events_bulk(body: BulkEventsIn):
        """Apply many events in order (stream simulation)."""
        out = []
        s = st()
        for e in body.events:
            r = process_event(s, BehaviorEvent(e.event_type, e.user_id, payload=e.payload))
            out.append(
                {
                    "event_type": r.event_type,
                    "applied": r.applied,
                    "detail": r.detail,
                    "score_before": r.score_before,
                    "score_after": r.score_after,
                    "score_delta": r.score_delta,
                    "tier_before": r.tier_before,
                    "tier_after": r.tier_after,
                }
            )
        return {"count": len(out), "results": out}

    def _enrich_events_with_score_deltas(store, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Pair each recent log row with its score snapshot (same newest-first order)."""
        hist_fn = getattr(store, "list_score_history", None)
        if not callable(hist_fn):
            return rows
        by_user: dict[str, list[dict[str, Any]]] = {}
        for ev in rows:
            uid = str(ev.get("user_id", "") or "")
            if uid and uid not in by_user:
                by_user[uid] = list(hist_fn(uid, limit=max(len(rows), 80)))
        enriched: list[dict[str, Any]] = []
        for ev in rows:
            row = dict(ev)
            uid = str(row.get("user_id", "") or "")
            snaps = by_user.get(uid)
            if snaps:
                snap = snaps.pop(0)
                row["score_after"] = snap.get("score")
                row["score_before"] = snap.get("score_before")
                row["score_delta"] = snap.get("score_delta")
                row["tier_after"] = snap.get("tier")
            enriched.append(row)
        return enriched

    @app.get("/api/events/recent")
    def recent_events(limit: int = 25, user_id: str | None = None):
        s = st()
        names = _user_name_index()
        uid = (user_id or "").strip() or None
        events = s.recent_events(limit=max(1, min(limit, 200)), user_id=uid)
        out = []
        for ev in events:
            et = ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type)
            out.append(
                {
                    "event_type": et,
                    "user_id": ev.user_id,
                    "user_name": _user_name_for(ev.user_id, names),
                    "payload": ev.payload,
                    "timestamp": (ev.timestamp or None).isoformat() if ev.timestamp else None,
                }
            )
        return {"events": _enrich_events_with_score_deltas(s, out)}

    @app.get("/api/reports/fairness")
    def report_fairness(window_days: int = 90, format: Literal["json", "csv"] = "json"):
        """Lightweight fairness report for users over a rolling time window."""
        s = st()
        days = max(1, min(window_days, 366))
        from newton3.domain.models import utcnow

        since = utcnow() - timedelta(days=days)
        profiles = s.list_profiles()
        profile_by_uid = {p.user_id: p for p in profiles}
        user_ids = sorted(profile_by_uid.keys())
        score_by_uid = {uid: s.get_score_state(uid).score for uid in user_ids}

        # Pull recent events in a large capped batch and aggregate by user in-window.
        events = s.recent_events(limit=200000)
        req_by_uid = {uid: 0 for uid in user_ids}
        unused_by_uid = {uid: 0 for uid in user_ids}
        nudge_by_uid = {uid: 0 for uid in user_ids}
        for ev in events:
            if not ev.timestamp or ev.timestamp < since:
                continue
            uid = ev.user_id
            if uid not in req_by_uid:
                continue
            et = ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type)
            if et == "booking.created":
                req_by_uid[uid] += 1
            elif et == "unused_booking":
                unused_by_uid[uid] += 1
            elif et in ("offence.reported", "offence"):
                nudge_by_uid[uid] += 1

        # Use persisted allocation winners as booking/win count proxy in this MVP report.
        runs = s.list_space_allocations(limit=5000)
        book_by_uid = {uid: 0 for uid in user_ids}
        for run in runs:
            created_at = run.get("created_at")
            if isinstance(created_at, str):
                try:
                    if created_at and created_at < since.isoformat():
                        continue
                except Exception:
                    pass
            for w in run.get("winners", []):
                uid = str(w.get("user_id", ""))
                if uid in book_by_uid:
                    book_by_uid[uid] += 1

        names = _user_name_index()
        rows: list[dict[str, Any]] = []
        for uid in user_ids:
            p = profile_by_uid[uid]
            requests = req_by_uid.get(uid, 0)
            bookings = book_by_uid.get(uid, 0)
            unused = unused_by_uid.get(uid, 0)
            nudge = nudge_by_uid.get(uid, 0)
            rejected = max(0, requests - bookings)
            approval = (bookings / requests * 100.0) if requests else 0.0
            rejection = (rejected / requests * 100.0) if requests else 0.0
            used_rate = (max(0, bookings - unused) / bookings * 100.0) if bookings else 0.0
            rows.append(
                {
                    "user_id": uid,
                    "user_name": _user_name_for(uid, names) or uid,
                    "company_name": "",
                    "office_name": "",
                    "group_name": p.group_id,
                    "guaranteed_team": "TRUE" if p.user_priority <= 1 else "FALSE",
                    "team_daily_priority": p.group_priority,
                    "individual_priority": p.user_priority,
                    "has_assigned_space": "Yes" if p.user_priority <= 1 else "No",
                    "requests_3mo": requests,
                    "bookings_3mo": bookings,
                    "rejected_3mo": rejected,
                    "unused_bookings_3mo": unused,
                    "nudge_offences_3mo": nudge,
                    "approval_rate_pct": round(approval, 1),
                    "rejection_rate_pct": round(rejection, 1),
                    "used_rate_pct": round(used_rate, 1),
                    "score": round(score_by_uid.get(uid, 0.0), 2),
                    "tier": derive_underserved_tier(
                        requests=requests,
                        rejection_rate_pct=rejection,
                        nudge_offences=nudge,
                    ),
                }
            )

        rows.sort(key=lambda r: (r["tier"], -r["rejection_rate_pct"], r["user_id"]))
        summary = {
            "window_days": days,
            "users": len(rows),
            "high_risk_users": sum(1 for r in rows if r["tier"] in ("M", "X")),
            "avg_rejection_rate_pct": round(
                (sum(float(r["rejection_rate_pct"]) for r in rows) / len(rows)) if rows else 0.0, 1
            ),
        }

        if format == "json":
            return {"summary": summary, "rows": rows}

        buf = io.StringIO()
        cols = [
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
            "score",
            "tier",
        ]
        wr = csv.DictWriter(buf, fieldnames=cols)
        wr.writeheader()
        for r in rows:
            wr.writerow(r)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="fairness-report-{days}d.csv"'},
        )

    @app.get("/api/reports/fairness/cohort")
    def report_fairness_cohort(
        seed: int | None = 1,
        format: Literal["json", "csv"] = "json",
    ):
        """
        Compare legacy underserved tiers with Newton behaviour scores.

        Import your Metabase CSV first: ``POST /api/admin/import-users-csv`` (UI file input).
        """
        from collections import defaultdict

        from newton3.domain.fairness import slug_group_id

        s = st()
        csv_path = _fairness_cohort_csv_path()
        if csv_path is None:
            raise HTTPException(
                404,
                "No imported CSV on server — upload Algorithm User Complaints export via Import users from CSV",
            )

        cohort: list[FairnessCohortRow] = []
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            for raw in csv.DictReader(f):
                row = FairnessCohortRow.from_csv_dict(raw)
                if row:
                    cohort.append(row)

        by_group: dict[str, list[str]] = defaultdict(list)
        registered: list[FairnessCohortRow] = []
        for row in cohort:
            if s.get_profile(row.user_id) is None:
                continue
            registered.append(row)
            by_group[slug_group_id(row.group_name)].append(row.user_id)

        if not registered:
            return {
                "summary": {"users": 0},
                "rows": [],
                "note": "No cohort users in store — POST /api/admin/import-fairness-cohort",
            }

        out: list[dict] = []
        for row in registered:
            gid = slug_group_id(row.group_name)
            pool = by_group.get(gid, [row.user_id])
            ranked = rank_users(s, pool, seed=seed)
            pos = next((r.rank for r in ranked if r.user_id == row.user_id), None)
            sc = s.get_score_state(row.user_id).score
            out.append(
                cohort_analysis_row(
                    row,
                    behavior_score=sc,
                    newton_rank=pos,
                    pool_size=len(pool),
                )
            )

        out.sort(
            key=lambda r: (
                r.get("legacy_underserved_tier", "Z"),
                -float(r.get("rejection_rate_pct") or 0),
            )
        )
        summary = cohort_summary(out)
        if format == "csv":
            buf = io.StringIO()
            cols = [
                "user_id",
                "user_name",
                "company_name",
                "group_name",
                "requests_3mo",
                "rejection_rate_pct",
                "legacy_underserved_tier",
                "computed_underserved_tier",
                "behavior_score",
                "behavior_tier",
                "newton_rank",
                "pool_size",
                "newton_behavior_helps_eligibility",
            ]
            wr = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
            wr.writeheader()
            for r in out:
                wr.writerow(r)
            return Response(
                content=buf.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="complaint-cohort-newton.csv"'},
            )
        return {
            "summary": summary,
            "rows": out,
            "seed": seed,
            "source_csv": str(csv_path),
            "total_rows": len(out),
        }

    def _decode_cohort_bytes(raw: bytes, *, filename: str) -> str:
        if len(raw) > MAX_COHORT_UPLOAD_BYTES:
            raise HTTPException(
                413,
                f"File exceeds {MAX_COHORT_UPLOAD_BYTES // (1024 * 1024)} MB limit",
            )
        if not raw.strip():
            raise HTTPException(400, "Uploaded file is empty")
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise HTTPException(400, "File must be UTF-8 text (CSV or TSV)") from e

    async def _read_cohort_upload(file: UploadFile) -> tuple[str, str]:
        raw = await file.read()
        name = (file.filename or "").strip() or "upload.csv"
        return _decode_cohort_bytes(raw, filename=name), name

    async def _cohort_upload_part(part: Any) -> tuple[str, str] | None:
        if part is None:
            return None
        read = getattr(part, "read", None)
        if callable(read):
            raw = await read()
            if not raw:
                return None
            name = (getattr(part, "filename", None) or "").strip() or "upload.csv"
            return _decode_cohort_bytes(raw, filename=name), name
        if isinstance(part, (bytes, bytearray)):
            return _decode_cohort_bytes(bytes(part), filename="upload.csv"), "upload.csv"
        return None

    async def _cohort_upload_from_request(
        request: Request,
        file: UploadFile | None = None,
    ) -> tuple[str, str] | None:
        """Read CSV/TSV from multipart form field ``file`` (browser file input)."""
        if file is not None:
            got = await _cohort_upload_part(file)
            if got is not None:
                return got
        ct = (request.headers.get("content-type") or "").lower()
        if "multipart/form-data" not in ct:
            return None
        form = await request.form()
        return await _cohort_upload_part(form.get("file"))

    async def _import_cohort_csv_text(text: str, name: str) -> dict[str, Any]:
        from newton3.services.cohort_import import DEFAULT_WORK_DIR, import_metabase_csv_to_store

        store = st()
        try:
            result = import_metabase_csv_to_store(
                text,
                store,
                DEFAULT_WORK_DIR,
                source_name=name,
            )
        except ValueError as e:
            detail = e.args[0]
            try:
                parsed = json.loads(detail)
                if isinstance(parsed, dict):
                    raise HTTPException(422, detail=parsed) from e
            except json.JSONDecodeError:
                pass
            raise HTTPException(422, detail=str(e)) from e
        result["sqlite_path"] = _store_sqlite_path(store)
        result["store"] = type(store).__name__
        return result

    @app.post("/api/admin/import-users-csv")
    async def admin_import_users_csv(
        request: Request,
        file: UploadFile | None = File(
            default=None,
            description="Raw Metabase/user export CSV or TSV (multipart field 'file')",
        ),
    ):
        """One step: raw Metabase CSV from file input → validate, transform, SQLite."""
        _require_admin()
        upload = await _cohort_upload_from_request(request, file)
        if upload is None:
            raise HTTPException(
                400,
                "Upload required: POST multipart form with field 'file' (your .csv export).",
            )
        text, name = upload
        return await _import_cohort_csv_text(text, name)

    @app.post("/api/admin/validate-fairness-cohort")
    async def admin_validate_fairness_cohort(
        request: Request,
        file: UploadFile | None = File(default=None),
    ):
        """Validate cohort export format without changing the store."""
        _require_admin()
        upload = await _cohort_upload_from_request(request, file)
        if upload is None:
            raise HTTPException(
                400,
                "POST multipart form with field 'file' (CSV or TSV from file input).",
            )
        text, name = upload
        return validate_fairness_cohort_text(text, filename=name)

    @app.post("/api/admin/import-fairness-cohort")
    async def admin_import_fairness_cohort(
        request: Request,
        file: UploadFile | None = File(default=None),
    ):
        """Alias for ``import-users-csv`` — raw Metabase file upload only."""
        _require_admin()
        return await admin_import_users_csv(request, file)

    @app.get("/api/users/{user_id}/behavior-score")
    def get_behavior_score(user_id: str):
        return _behavior_score_payload(st(), user_id)

    @app.get("/api/users/{user_id}/score-history")
    def score_history(user_id: str, limit: int = 50):
        fn = getattr(st(), "list_score_history", None)
        if not callable(fn):
            return {"user_id": user_id, "snapshots": [], "note": "history not available for this store"}
        return {"user_id": user_id, "snapshots": fn(user_id, limit=limit)}

    @app.get("/api/users/{user_id}/insights")
    def user_insights(user_id: str):
        s = st()
        if s.get_profile(user_id) is None:
            raise HTTPException(404, "user not registered")
        names = _user_name_index()
        uname = _user_name_for(user_id, names)
        return {
            "user_id": user_id,
            "user_name": uname,
            "anomaly": {**score_anomaly(s, user_id), "user_name": uname},
            "no_show": {**no_show_risk(s, user_id), "user_name": uname},
            "ensemble": {**ensemble_anomaly_flags(s, user_id), "user_name": uname},
        }

    @app.get("/api/allocation/rank")
    def allocation_rank(
        user_ids: str,
        seed: int | None = None,
        include_scores: bool = False,
    ):
        s = st()
        ids = [x.strip() for x in user_ids.split(",") if x.strip()]
        names = _user_name_index()
        rows = rank_users(s, ids, seed=seed)
        ranking = []
        for r in rows:
            row = {
                "rank": r.rank,
                "user_id": r.user_id,
                "user_name": _user_name_for(r.user_id, names),
                "explain": r.explain,
            }
            if include_scores:
                sc = s.get_score_state(r.user_id)
                row["behavior_score"] = sc.score
                row["tier"] = tier_for_score(sc.score).value
            ranking.append(row)
        return {"ranking": ranking}

    @app.get("/api/allocation/allocate")
    def allocation_allocate(
        user_ids: str,
        capacity: int,
        seed: int | None = None,
        wait_limit: int = 50,
    ):
        """Assign parking spaces to top-ranked users; returns plain-language outcome."""
        s = st()
        ids = [x.strip() for x in user_ids.split(",") if x.strip()]
        cap = max(0, capacity)
        rows = allocate_spaces(s, ids, capacity=cap, seed=seed)
        allocation_id = s.record_space_allocation(ids, cap, seed, rows)
        names = _user_name_index()
        wl = max(0, min(wait_limit, 200))
        outcome = build_allocation_outcome(s, ids, cap, seed=seed, waitlist_limit=wl)

        def enrich(row: dict) -> dict:
            uid = row["user_id"]
            return {**row, "user_name": _user_name_for(uid, names)}

        return {
            "allocation_id": allocation_id,
            "capacity": cap,
            "pool_size": outcome["pool_size"],
            "seed": seed,
            "winners": [enrich(r) for r in outcome["assigned"]],
            "assigned": [enrich(r) for r in outcome["assigned"]],
            "waiting": [enrich(r) for r in outcome["waiting"]],
            "waiting_total": outcome["waiting_total"],
            "how_it_works": (
                f"We ranked {outcome['pool_size']} drivers in one list. "
                f"The first {cap} got a parking space (Space #1, #2, …). "
                "Ranking uses team rules, then individual priority, then behaviour score."
            ),
        }

    @app.get("/api/allocation/runs")
    def allocation_runs_list(limit: int = 50):
        """Saved allocation runs (newest first)."""
        lim = max(1, min(limit, 500))
        names = _user_name_index()
        return {"runs": _enrich_allocation_runs(st().list_space_allocations(lim), names)}

    @app.get("/api/allocation/runs/{run_id}")
    def allocation_run_get(run_id: int):
        row = st().get_space_allocation(run_id)
        if row is None:
            raise HTTPException(404, "allocation run not found")
        names = _user_name_index()
        enriched = _enrich_allocation_runs([row], names)
        return enriched[0]

    @app.get("/api/allocations")
    def allocations_history(limit: int = 50):
        """Saved allocation runs (newest first). Alias avoids nested ``/allocation/runs`` path issues."""
        lim = max(1, min(limit, 500))
        names = _user_name_index()
        return {"runs": _enrich_allocation_runs(st().list_space_allocations(lim), names)}

    @app.get("/api/allocation/explain")
    def allocation_explain(user_ids: str, focus: str, seed: int | None = None):
        ids = [x.strip() for x in user_ids.split(",") if x.strip()]
        names = _user_name_index()
        return _enrich_explain_payload(
            allocation_explain_for_user(st(), ids, focus, seed=seed),
            names,
        )

    @app.get("/api/allocation/shadow")
    def allocation_shadow(user_ids: str, seed: int | None = None):
        """Compare Newton 3 vs mock-legacy (priorities only, no behaviour)."""
        ids = [x.strip() for x in user_ids.split(",") if x.strip()]
        s = st()
        names = _user_name_index()
        newton = rank_users(s, ids, seed=seed)
        legacy = rank_legacy(s, ids, seed=seed)
        diff = shadow_diff(newton, legacy)
        return {
            "newton": [
                _enrich_user_row({"rank": r.rank, "user_id": r.user_id, "explain": r.explain}, names)
                for r in newton
            ],
            "legacy_mock": [
                _enrich_user_row({"rank": r.rank, "user_id": r.user_id, "explain": r.explain}, names)
                for r in legacy
            ],
            "diff": [_enrich_user_row(d, names) for d in diff],
        }

    @app.post("/api/allocation/explain-llm")
    def allocation_explain_llm(body: LlmExplainIn):
        s = st()
        ids = [x.strip() for x in body.user_ids.split(",") if x.strip()]
        names = _user_name_index()
        rows = rank_users(s, ids, seed=body.seed)
        ranking = [
            _enrich_user_row({"rank": r.rank, "user_id": r.user_id, "explain": r.explain}, names)
            for r in rows
        ]
        snap = gather_llm_store_snapshot(
            s, ids, seed=body.seed, allocation_capacity=body.allocation_capacity
        )
        return enrich_with_llm(
            ranking,
            context=body.context,
            messages=[m.model_dump() for m in body.messages],
            follow_up=body.follow_up,
            store_snapshot=snap,
        )

    _react_dist = REPO_ROOT / "ui" / "dist"
    _legacy_static = REPO_ROOT / "static"
    ui_dir: Path | None = None
    raw_override = os.environ.get("NEWTON3_UI_DIST")
    if raw_override:
        po = Path(raw_override).expanduser()
        if po.is_dir() and (po / "index.html").is_file():
            ui_dir = po
    if ui_dir is None and _react_dist.is_dir() and (_react_dist / "index.html").is_file():
        ui_dir = _react_dist
    if ui_dir is None and _legacy_static.is_dir():
        ui_dir = _legacy_static
    if ui_dir is not None:
        app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    return app


_lazy_default_app: FastAPI | None = None


def __getattr__(name: str):
    """Lazily build default ASGI app so ``import api`` does not touch SQLite (tests).

    The instance is cached: repeated ``api.app`` access returns the same object.
    """
    global _lazy_default_app
    if name == "app":
        if _lazy_default_app is None:
            _lazy_default_app = create_app()
        return _lazy_default_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
