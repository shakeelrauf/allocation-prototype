from unittest.mock import patch

from newton3.local_ollama import ensure_ollama_running, ollama_reachable


def test_ensure_skipped_when_llm_url_set(monkeypatch):
    monkeypatch.setenv("NEWTON3_LLM_URL", "http://example/v1/chat/completions")
    out = ensure_ollama_running(verbose=False)
    assert out.get("skipped")
    assert out["enabled"] is False


def test_ensure_already_reachable(monkeypatch):
    monkeypatch.delenv("NEWTON3_LLM_URL", raising=False)
    with patch("newton3.local_ollama.ollama_reachable", return_value=True):
        out = ensure_ollama_running(verbose=False)
    assert out["enabled"] is True
    assert out["reachable"] is True


def test_ensure_starts_serve_when_down(monkeypatch):
    monkeypatch.delenv("NEWTON3_LLM_URL", raising=False)
    with (
        patch("newton3.local_ollama.ollama_reachable", side_effect=[False, False, True]),
        patch("newton3.local_ollama._open_ollama_app_macos", return_value=False),
        patch("newton3.local_ollama._start_ollama_serve", return_value=True),
        patch("newton3.local_ollama.shutil.which", return_value="/usr/local/bin/ollama"),
    ):
        out = ensure_ollama_running(verbose=False, wait_timeout_sec=5.0)
    assert out["started_serve"] is True
    assert out["reachable"] is True
