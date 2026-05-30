import json
from unittest.mock import patch

from newton3.services.llm_explain import enrich_with_llm, gather_llm_store_snapshot, llm_feature_flags, template_explanation
from newton3.domain.models import BehaviorEvent, EventType, UserProfile
from newton3.persistence.store import InMemoryStore


def test_template_when_no_llm_env(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_AUTO", "0")
    monkeypatch.delenv("NEWTON3_LLM_URL", raising=False)
    ranking = [{"rank": 1, "user_id": "a", "explain": "prio"}]
    out = enrich_with_llm(ranking, context="")
    assert out["mode"] == "template"
    assert "Rank 1" in out["text"]
    assert "hint" in out
    assert "echo_user" in out and "Explain this parking allocation" in out["echo_user"]


def test_llm_feature_flags_off(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_AUTO", "0")
    monkeypatch.delenv("NEWTON3_LLM_URL", raising=False)
    monkeypatch.delenv("NEWTON3_LLM_CHARACTER_NAME", raising=False)
    f = llm_feature_flags()
    assert f["llm_explain_env"] is False
    assert f["llm_backend"] == "off"
    assert f["llm_auto_ollama"] is False
    assert f["llm_character"] == "Shakeel"


def test_llm_feature_flags_custom_character(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_AUTO", "0")
    monkeypatch.setenv("NEWTON3_LLM_CHARACTER_NAME", "Morgan")
    f = llm_feature_flags()
    assert f["llm_character"] == "Morgan"


def test_llm_feature_flags_ollama_explicit_url(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_URL", "http://127.0.0.1:11434/v1/chat/completions")
    f = llm_feature_flags()
    assert f["llm_explain_env"] is True
    assert f["llm_backend"] == "ollama"
    assert f["llm_auto_ollama"] is False


def test_llm_feature_flags_auto_ollama(monkeypatch):
    monkeypatch.delenv("NEWTON3_LLM_URL", raising=False)

    class FakeResp:
        def __init__(self, data=b"{}"):
            self._data = data

        def read(self, n=-1):
            if n == -1:
                return self._data
            return self._data[: min(n, len(self._data))]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("newton3.services.llm_explain.urlopen", return_value=FakeResp()):
        f = llm_feature_flags()
    assert f["llm_explain_env"] is True
    assert f["llm_backend"] == "ollama"
    assert f["llm_auto_ollama"] is True


def test_enrich_auto_ollama_when_probe_ok(monkeypatch):
    monkeypatch.delenv("NEWTON3_LLM_URL", raising=False)
    monkeypatch.setenv("NEWTON3_LLM_MODEL", "mistral")
    ranking = [{"rank": 1, "user_id": "x", "explain": "ok"}]

    class FakeResp:
        def __init__(self, data=b"{}"):
            self._data = data

        def read(self, n=-1):
            if n == -1:
                return self._data
            return self._data[: min(n, len(self._data))]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_open(req, *args, **kwargs):
        url = req.full_url
        if "/api/tags" in url:
            return FakeResp(b'{"models":[]}')
        if "chat/completions" in url:
            payload = json.dumps({"choices": [{"message": {"content": "Hello auto"}}]}).encode()
            return FakeResp(payload)
        raise AssertionError(url)

    with patch("newton3.services.llm_explain.urlopen", side_effect=fake_open):
        out = enrich_with_llm(ranking)

    assert out["mode"] == "ollama"
    assert out["text"] == "Hello auto"
    assert out.get("llm_source") == "auto"
    assert "echo_user" in out


def test_enrich_multiturn_includes_history(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_URL", "http://ollama/v1/chat/completions")
    monkeypatch.setenv("NEWTON3_LLM_MODEL", "mistral")
    ranking = [{"rank": 1, "user_id": "x", "explain": "ok"}]
    captured: list[dict[str, str]] = []

    fake_resp = {"choices": [{"message": {"content": "reply"}}]}
    payload = json.dumps(fake_resp).encode()

    class FakeResp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_open(req, *args, **kwargs):
        data = getattr(req, "data", None)
        if data:
            body = json.loads(data.decode())
            for m in body.get("messages") or []:
                captured.append({"role": m["role"], "content": m["content"]})
        return FakeResp()

    hist = [{"role": "user", "content": "First question"}, {"role": "assistant", "content": "First answer"}]
    with patch("newton3.services.llm_explain.urlopen", side_effect=fake_open):
        out = enrich_with_llm(ranking, messages=hist, follow_up="Why x?")

    assert out["mode"] == "ollama"
    assert out["text"] == "reply"
    assert out["echo_user"].startswith("Order (best rank first)")
    assert "Follow-up:\nWhy x?" in out["echo_user"]
    assert captured[0]["role"] == "system"
    assert captured[1]["role"] == "user"
    assert captured[1]["content"].startswith("First question")
    assert captured[2]["role"] == "assistant"
    assert captured[3]["role"] == "user"
    assert "Follow-up:" in captured[3]["content"]


def test_ollama_used_when_url_set(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_URL", "http://ollama/v1/chat/completions")
    monkeypatch.setenv("NEWTON3_LLM_MODEL", "mistral")
    ranking = [{"rank": 1, "user_id": "x", "explain": "ok"}]

    fake_resp = {"choices": [{"message": {"content": "Hello from ollama"}}]}
    payload = json.dumps(fake_resp).encode()

    class FakeResp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("newton3.services.llm_explain.urlopen", return_value=FakeResp()):
        out = enrich_with_llm(ranking)

    assert out["mode"] == "ollama"
    assert out["text"] == "Hello from ollama"
    assert out.get("llm_source") == "env"
    assert "template_fallback" in out
    assert "echo_user" in out


def test_ollama_json_blob_replaced_with_template(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_URL", "http://ollama/v1/chat/completions")
    monkeypatch.setenv("NEWTON3_LLM_MODEL", "mistral")
    ranking = [{"rank": 1, "user_id": "u", "explain": "rank=1: ok"}]
    blob = '{"title": "Newton", "summary": "bad", "bullets": [], "rank_notes": [], "fairness": ""}'
    payload = json.dumps({"choices": [{"message": {"content": blob}}]}).encode()

    class FakeResp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("newton3.services.llm_explain.urlopen", return_value=FakeResp()):
        out = enrich_with_llm(ranking)

    assert out["mode"] == "ollama"
    assert blob not in out["text"]
    assert "Allocation summary (Newton 3)" in out["text"]
    assert "deterministic summary" in out["text"].lower()


def test_template_explanation_structure():
    r = [{"rank": 2, "user_id": "bob", "explain": "tier"}]
    t = template_explanation(r)
    assert "bob" in t and "Newton 3" in t


def test_gather_llm_store_snapshot_groups_events_allocation():
    st = InMemoryStore()
    st.ensure_group("eng", 1)
    st.ensure_user(UserProfile("alice", "eng", 1, 5))
    st.log_event(BehaviorEvent(EventType.UNUSED_BOOKING, "alice", payload={"slot": "A1"}))
    snap = gather_llm_store_snapshot(st, ["alice"], seed=11, allocation_capacity=1)
    assert "**Groups**" in snap and "eng" in snap
    assert "alice" in snap and "behaviour_score" in snap
    assert "unused_booking" in snap
    assert "**Space allocation**" in snap and "Spot #1" in snap


def test_enrich_echo_user_includes_store_snapshot(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_AUTO", "0")
    monkeypatch.delenv("NEWTON3_LLM_URL", raising=False)
    ranking = [{"rank": 1, "user_id": "a", "explain": "prio"}]
    out = enrich_with_llm(ranking, context="", store_snapshot="**Groups**\n- g1: group_priority=1")
    assert "### Newton data snapshot" in out["echo_user"]
    assert "g1" in out["echo_user"]
