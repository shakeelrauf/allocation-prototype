import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from api import create_app
from models import BehaviorEvent, UserProfile
from store import InMemoryStore


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
    assert r.json()["score_after"] == 97
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
