"""FastAPI service + static UI. Uses SQLite via SqliteStore unless a store is injected."""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from datetime import timedelta
from typing import Any, Literal

try:
    from fastapi import FastAPI, HTTPException, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field, field_validator
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "Install API deps: pip install -e '.[api]' "
        "or pip install -r requirements-dev.txt"
    ) from e

from allocation_engine import allocate_spaces, allocation_explain_for_user, rank_users
from event_processor import process_event, seed_users
from insights import ensemble_anomaly_flags, no_show_risk, score_anomaly
from llm_explain import enrich_with_llm, gather_llm_store_snapshot, llm_feature_flags
from models import BehaviorEvent, UserProfile, tier_for_score
from shadow_engine import rank_legacy, shadow_diff
from sqlite_store import SqliteStore, default_sqlite_path
from store import ScoreStore
from tenant_weights import TenantWeights


def _derive_underserved_tier(*, requests: int, rejection_rate_pct: float, nudge_offences: int) -> str:
    """Heuristic underserved tier for quick fairness reporting."""
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
    raw = os.environ.get("NEWTON3_DB_PATH")
    if raw:
        return SqliteStore(raw)
    return SqliteStore(default_sqlite_path())


def _behavior_score_payload(st: ScoreStore, user_id: str) -> dict[str, Any]:
    prof = st.get_profile(user_id)
    if prof is None:
        raise HTTPException(404, "user not registered")
    sc = st.get_score_state(user_id)
    return {
        "user_id": user_id,
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
            "features": {
                "shadow_mode": True,
                "score_history": hasattr(store, "list_score_history"),
                "tenant_weights": hasattr(store, "set_tenant_weights"),
                "groups_registry": hasattr(store, "list_groups"),
                "llm_explain_env": llm_flags["llm_explain_env"],
                "llm_backend": llm_flags["llm_backend"],
                "llm_auto_ollama": llm_flags["llm_auto_ollama"],
                "llm_character": llm_flags["llm_character"],
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
        rows = []
        for prof in s.list_profiles():
            sc = s.get_score_state(prof.user_id)
            rows.append(
                {
                    "user_id": prof.user_id,
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
        fn = getattr(st(), "clear_all_data", None)
        if not callable(fn):
            raise HTTPException(501, "this store does not support reset")
        fn()
        return {"ok": True}

    @app.post("/api/admin/groups")
    def admin_create_group(body: GroupIn):
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
        r = process_event(
            st(),
            BehaviorEvent(body.event_type, body.user_id, payload=body.payload),
        )
        return {
            "applied": r.applied,
            "detail": r.detail,
            "score_after": r.score_after,
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
                    "score_after": r.score_after,
                }
            )
        return {"count": len(out), "results": out}

    @app.get("/api/events/recent")
    def recent_events(limit: int = 25):
        s = st()
        events = s.recent_events(limit=max(1, min(limit, 200)))
        out = []
        for ev in events:
            et = ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type)
            out.append(
                {
                    "event_type": et,
                    "user_id": ev.user_id,
                    "payload": ev.payload,
                    "timestamp": (ev.timestamp or None).isoformat() if ev.timestamp else None,
                }
            )
        return {"events": out}

    @app.get("/api/reports/fairness")
    def report_fairness(window_days: int = 90, format: Literal["json", "csv"] = "json"):
        """Lightweight fairness report for users over a rolling time window."""
        s = st()
        days = max(1, min(window_days, 366))
        from models import utcnow

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
                    "user_name": uid,
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
                    "tier": _derive_underserved_tier(
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
        return {
            "user_id": user_id,
            "anomaly": score_anomaly(s, user_id),
            "no_show": no_show_risk(s, user_id),
            "ensemble": ensemble_anomaly_flags(s, user_id),
        }

    @app.get("/api/allocation/rank")
    def allocation_rank(
        user_ids: str,
        seed: int | None = None,
        include_scores: bool = False,
    ):
        s = st()
        ids = [x.strip() for x in user_ids.split(",") if x.strip()]
        rows = rank_users(s, ids, seed=seed)
        ranking = []
        for r in rows:
            row = {"rank": r.rank, "user_id": r.user_id, "explain": r.explain}
            if include_scores:
                sc = s.get_score_state(r.user_id)
                row["behavior_score"] = sc.score
                row["tier"] = tier_for_score(sc.score).value
            ranking.append(row)
        return {"ranking": ranking}

    @app.get("/api/allocation/allocate")
    def allocation_allocate(user_ids: str, capacity: int, seed: int | None = None):
        """Return top `capacity` users after full Newton ranking and persist the decision."""
        s = st()
        ids = [x.strip() for x in user_ids.split(",") if x.strip()]
        cap = max(0, capacity)
        rows = allocate_spaces(s, ids, capacity=cap, seed=seed)
        allocation_id = s.record_space_allocation(ids, cap, seed, rows)
        return {
            "allocation_id": allocation_id,
            "capacity": capacity,
            "winners": [
                {
                    "rank": r.rank,
                    "user_id": r.user_id,
                    "explain": r.explain,
                    "behavior_score": s.get_score_state(r.user_id).score,
                    "tier": tier_for_score(s.get_score_state(r.user_id).score).value,
                }
                for r in rows
            ],
        }

    @app.get("/api/allocation/runs")
    def allocation_runs_list(limit: int = 50):
        """Saved allocation runs (newest first)."""
        lim = max(1, min(limit, 500))
        return {"runs": st().list_space_allocations(lim)}

    @app.get("/api/allocation/runs/{run_id}")
    def allocation_run_get(run_id: int):
        row = st().get_space_allocation(run_id)
        if row is None:
            raise HTTPException(404, "allocation run not found")
        return row

    @app.get("/api/allocations")
    def allocations_history(limit: int = 50):
        """Saved allocation runs (newest first). Alias avoids nested ``/allocation/runs`` path issues."""
        lim = max(1, min(limit, 500))
        return {"runs": st().list_space_allocations(lim)}

    @app.get("/api/allocation/explain")
    def allocation_explain(user_ids: str, focus: str, seed: int | None = None):
        ids = [x.strip() for x in user_ids.split(",") if x.strip()]
        return allocation_explain_for_user(st(), ids, focus, seed=seed)

    @app.get("/api/allocation/shadow")
    def allocation_shadow(user_ids: str, seed: int | None = None):
        """Compare Newton 3 vs mock-legacy (priorities only, no behaviour)."""
        ids = [x.strip() for x in user_ids.split(",") if x.strip()]
        s = st()
        newton = rank_users(s, ids, seed=seed)
        legacy = rank_legacy(s, ids, seed=seed)
        return {
            "newton": [{"rank": r.rank, "user_id": r.user_id, "explain": r.explain} for r in newton],
            "legacy_mock": [
                {"rank": r.rank, "user_id": r.user_id, "explain": r.explain} for r in legacy
            ],
            "diff": shadow_diff(newton, legacy),
        }

    @app.post("/api/allocation/explain-llm")
    def allocation_explain_llm(body: LlmExplainIn):
        s = st()
        ids = [x.strip() for x in body.user_ids.split(",") if x.strip()]
        rows = rank_users(s, ids, seed=body.seed)
        ranking = [{"rank": r.rank, "user_id": r.user_id, "explain": r.explain} for r in rows]
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

    _root = Path(__file__).resolve().parent
    _react_dist = _root / "ui" / "dist"
    _legacy_static = _root / "static"
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
