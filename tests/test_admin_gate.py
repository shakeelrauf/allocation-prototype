from fastapi.testclient import TestClient

from newton3.api.app import create_app
from newton3.persistence.store import InMemoryStore


def test_admin_reset_blocked_when_disabled(monkeypatch):
    monkeypatch.setenv("NEWTON3_ADMIN_ENABLED", "false")
    c = TestClient(create_app(InMemoryStore()))
    r = c.post("/api/admin/reset")
    assert r.status_code == 403
