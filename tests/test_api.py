import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from newton3.api.app import create_app
from newton3.domain.models import BehaviorEvent, UserProfile
from newton3.persistence.store import InMemoryStore


def test_api_health_and_users():
    st = InMemoryStore()
    st.ensure_user(UserProfile("alice", "eng", group_priority=1, user_priority=5))
    app = create_app(st)
    c = TestClient(app)
    assert c.get("/api/health").json()["status"] == "ok"
    body = c.get("/api/users").json()
    assert len(body["users"]) == 1
    assert body["users"][0]["user_id"] == "alice"


def test_health_includes_sqlite_path_for_sqlite_store(monkeypatch):
    path = Path(tempfile.mkdtemp()) / "health.db"
    monkeypatch.setenv("NEWTON3_DB_PATH", str(path))
    app = create_app()
    c = TestClient(app)
    h = c.get("/api/health").json()
    assert h["store"] == "SqliteStore"
    assert "sqlite_path" in h
    assert Path(h["sqlite_path"]).is_absolute()


def test_api_event_and_rank():
    st = InMemoryStore()
    st.ensure_user(UserProfile("a", "g", 1, 1))
    st.ensure_user(UserProfile("b", "g", 1, 1))
    app = create_app(st)
    c = TestClient(app)
    r = c.post(
        "/api/events",
        json={"event_type": "unused_booking", "user_id": "b", "payload": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["score_after"] == 97
    assert body["score_delta"] == -3
    rank = c.get("/api/allocation/rank", params={"user_ids": "a,b", "seed": 1}).json()
    assert len(rank["ranking"]) == 2


def test_groups_list_and_admin_create():
    st = InMemoryStore()
    st.ensure_group("sales", 5)
    c = TestClient(create_app(st))
    body = c.get("/api/groups").json()
    assert any(g["group_id"] == "sales" for g in body["groups"])
    r = c.post("/api/admin/groups", json={"group_id": "hq", "group_priority": 1})
    assert r.status_code == 200
    ids = {g["group_id"] for g in c.get("/api/groups").json()["groups"]}
    assert "hq" in ids


def test_spec_behavior_score_path_alias():
    st = InMemoryStore()
    st.ensure_user(UserProfile("alice", "eng", group_priority=1, user_priority=5))
    c = TestClient(create_app(st))
    r = c.get("/users/alice/behavior-score")
    assert r.status_code == 200
    assert r.json()["tier"] == "Silver"


def test_allocation_explain_and_shadow_and_insights():
    st = InMemoryStore()
    st.ensure_user(UserProfile("a", "g", 1, 1))
    st.ensure_user(UserProfile("b", "g", 1, 1))
    st.get_score_state("a").score = 125
    c = TestClient(create_app(st))
    ex = c.get("/api/allocation/explain", params={"user_ids": "a,b", "focus": "b", "seed": 1}).json()
    assert ex["rank"] >= 1
    assert "narrative" in ex
    assert "focus_detail" in ex
    assert ex["focus_detail"]["behavior_score"] is not None
    assert len(ex["focus_detail"]["calculation_steps"]) >= 6
    sh = c.get("/api/allocation/shadow", params={"user_ids": "a,b", "seed": 1}).json()
    assert "newton" in sh and "legacy_mock" in sh
    ins = c.get("/api/users/a/insights").json()
    assert ins["ensemble"]["user_id"] == "a"


def test_bulk_events_and_allocate():
    st = InMemoryStore()
    st.ensure_user(UserProfile("a", "g", 1, 1))
    st.ensure_user(UserProfile("b", "g", 1, 1))
    st.ensure_user(UserProfile("c", "g", 2, 1))
    c = TestClient(create_app(st))
    r = c.post(
        "/api/events/bulk",
        json={
            "events": [
                {"event_type": "unused_booking", "user_id": "b", "payload": {}},
                {"event_type": "carpool.detected", "user_id": "a", "payload": {}},
            ]
        },
    )
    assert r.status_code == 200
    assert r.json()["count"] == 2
    all_ev = c.get("/api/events/recent", params={"limit": 50}).json()["events"]
    assert len(all_ev) >= 2
    bob_only = c.get("/api/events/recent", params={"limit": 50, "user_id": "b"}).json()["events"]
    assert bob_only and all(e["user_id"] == "b" for e in bob_only)
    alloc = c.get("/api/allocation/allocate", params={"user_ids": "a,b,c", "capacity": 2, "seed": 1}).json()
    assert len(alloc["winners"]) == 2
    aid = alloc["allocation_id"]
    assert isinstance(aid, int) and aid >= 1
    hist = c.get("/api/allocation/runs", params={"limit": 10}).json()
    assert any(r["id"] == aid for r in hist["runs"])
    hist_alias = c.get("/api/allocations", params={"limit": 10}).json()
    assert hist_alias["runs"] == hist["runs"]
    one = c.get(f"/api/allocation/runs/{aid}").json()
    assert one["capacity"] == 2 and one["seed"] == 1
    assert one["pool_user_ids"] == ["a", "b", "c"]
    assert len(one["winners"]) == 2


def test_admin_reset_clears_store():
    st = InMemoryStore()
    st.ensure_group("g1", 1)
    st.ensure_user(UserProfile("u", "g1", group_priority=1, user_priority=1))
    st.log_event(BehaviorEvent("unused_booking", "u", payload={}))
    c = TestClient(create_app(st))
    assert len(c.get("/api/users").json()["users"]) == 1
    assert c.post("/api/admin/reset").status_code == 200
    assert c.get("/api/users").json()["users"] == []
    assert c.get("/api/groups").json()["groups"] == []


def test_tenant_config_roundtrip():
    st = InMemoryStore()
    st.ensure_user(UserProfile("u", "tenant-a", 1, 1))
    c = TestClient(create_app(st))
    c.post("/api/admin/tenant-config", json={"group_id": "tenant-a", "weights": {"no_show": 9}})
    r = c.get("/api/admin/tenant-config/tenant-a").json()
    assert r["weights"]["no_show"] == 9
    c.post("/api/events", json={"event_type": "unused_booking", "user_id": "u", "payload": {}})
    assert c.get("/api/users/u/behavior-score").json()["score"] == 91


def test_fairness_cohort_import_and_report():
    from tests.metabase_csv import minimal_metabase_csv

    c = TestClient(create_app(InMemoryStore()))
    csv_bytes = minimal_metabase_csv(rows=25).encode("utf-8")
    imp = c.post(
        "/api/admin/import-users-csv",
        files={"file": ("metabase.csv", csv_bytes, "text/csv")},
    )
    assert imp.status_code == 200
    body = c.get("/api/reports/fairness/cohort", params={"seed": 1}).json()
    assert body["summary"]["users"] >= 10
    assert any(r.get("legacy_underserved_tier") for r in body["rows"])


def test_validate_fairness_cohort_upload():
    from tests.metabase_csv import minimal_metabase_csv

    c = TestClient(create_app(InMemoryStore()))
    csv_bytes = minimal_metabase_csv(rows=25).encode("utf-8")
    r = c.post(
        "/api/admin/validate-fairness-cohort",
        files={"file": ("sample.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["valid_rows"] >= 10

    bad = c.post(
        "/api/admin/validate-fairness-cohort",
        files={"file": ("bad.csv", b"only,one\n1,x\n", "text/csv")},
    )
    assert bad.status_code == 200
    assert bad.json()["ok"] is False


def test_import_requires_uploaded_file():
    c = TestClient(create_app(InMemoryStore()))
    assert c.post("/api/admin/import-users-csv").status_code == 400
    assert c.post("/api/admin/import-fairness-cohort").status_code == 400


def test_import_cohort_upload_clears_and_persists_sqlite(tmp_path, monkeypatch):
    from tests.metabase_csv import minimal_metabase_csv

    db = tmp_path / "cohort.db"
    monkeypatch.setenv("NEWTON3_DB_PATH", str(db))
    c = TestClient(create_app())
    c.post("/api/admin/users", json=[{"user_id": "orphan", "group_id": "g1"}])
    assert len(c.get("/api/users").json()["users"]) >= 1

    r = c.post(
        "/api/admin/import-users-csv",
        files={"file": ("sample.csv", minimal_metabase_csv(rows=25).encode("utf-8"), "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["users_in_db"] >= 10
    assert body.get("sqlite_path") == str(db)
    users = c.get("/api/users").json()["users"]
    assert len(users) == body["users_in_db"]
    assert not any(u["user_id"] == "orphan" for u in users)
    assert db.is_file()


def test_import_users_csv_upload():
    from tests.metabase_csv import minimal_metabase_csv

    c = TestClient(create_app(InMemoryStore()))
    r = c.post(
        "/api/admin/import-users-csv",
        files={"file": ("metabase.csv", minimal_metabase_csv(rows=25).encode("utf-8"), "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["source"] == "upload"
    assert r.json()["users_in_db"] >= 10

    no_file = c.post("/api/admin/import-users-csv")
    assert no_file.status_code == 400


def test_import_fairness_cohort_upload():
    from tests.metabase_csv import minimal_metabase_csv

    c = TestClient(create_app(InMemoryStore()))
    r = c.post(
        "/api/admin/import-fairness-cohort",
        files={"file": ("sample.csv", minimal_metabase_csv(rows=25).encode("utf-8"), "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["source"] == "upload"
    assert r.json()["validation"]["ok"] is True


def test_fairness_report_json_and_csv():
    st = InMemoryStore()
    st.ensure_user(UserProfile("alice", "g1", 1, 2))
    st.ensure_user(UserProfile("bob", "g1", 1, 3))
    c = TestClient(create_app(st))
    c.post("/api/events", json={"event_type": "booking.created", "user_id": "alice", "payload": {}})
    c.post("/api/events", json={"event_type": "unused_booking", "user_id": "alice", "payload": {}})
    c.get("/api/allocation/allocate", params={"user_ids": "alice,bob", "capacity": 1, "seed": 1})

    body = c.get("/api/reports/fairness", params={"window_days": 90, "format": "json"}).json()
    assert "summary" in body and "rows" in body
    assert any(r["user_id"] == "alice" for r in body["rows"])

    csv_res = c.get("/api/reports/fairness", params={"window_days": 90, "format": "csv"})
    assert csv_res.status_code == 200
    assert csv_res.headers["content-type"].startswith("text/csv")
    assert "user_id" in csv_res.text
