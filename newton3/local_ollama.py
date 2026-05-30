"""Start and probe local Ollama for ``run_local.py`` (optional; skipped on AWS / explicit URL)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 11434


def _ollama_host() -> str:
    return (os.environ.get("NEWTON3_OLLAMA_HOST") or _DEFAULT_HOST).strip() or _DEFAULT_HOST


def _tags_url(host: str | None = None, port: int = _DEFAULT_PORT) -> str:
    h = (host or _ollama_host()).strip() or _DEFAULT_HOST
    return f"http://{h}:{port}/api/tags"


def ollama_reachable(*, host: str | None = None, port: int = _DEFAULT_PORT, timeout: float = 1.0) -> bool:
    try:
        req = Request(_tags_url(host, port))
        with urlopen(req, timeout=timeout) as resp:
            resp.read(65536)
        return True
    except (URLError, OSError, TimeoutError):
        return False


def _should_manage_ollama() -> bool:
    if (os.environ.get("NEWTON3_LLM_BACKEND") or "").strip().lower() in ("bedrock", "aws"):
        return False
    if os.environ.get("NEWTON3_BEDROCK_MODEL_ID", "").strip():
        return False
    if os.environ.get("NEWTON3_LLM_URL", "").strip():
        return False
    auto = os.environ.get("NEWTON3_LLM_AUTO", "1").strip().lower()
    return auto not in ("0", "false", "no", "off")


def _open_ollama_app_macos() -> bool:
    if platform.system() != "Darwin":
        return False
    app = "/Applications/Ollama.app"
    if not os.path.isdir(app):
        return False
    try:
        subprocess.run(["open", "-a", "Ollama"], check=False, timeout=10)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _start_ollama_serve() -> bool:
    exe = shutil.which("ollama")
    if not exe:
        return False
    try:
        subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError:
        return False


def _wait_for_ollama(*, host: str | None, port: int, timeout_sec: float) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if ollama_reachable(host=host, port=port, timeout=0.8):
            return True
        time.sleep(0.5)
    return False


def _pull_model(model: str, *, timeout_sec: float = 900.0) -> bool:
    exe = shutil.which("ollama")
    if not exe:
        return False
    try:
        subprocess.run(
            [exe, "pull", model],
            check=True,
            timeout=timeout_sec,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def ensure_ollama_running(
    *,
    pull_model: bool = False,
    model: str | None = None,
    wait_timeout_sec: float = 60.0,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Ensure Ollama responds on ``NEWTON3_OLLAMA_HOST``:11434 before starting the API.

    Order: probe → macOS open Ollama.app → ``ollama serve`` → wait → optional ``ollama pull``.
    """
    out: dict[str, Any] = {
        "enabled": False,
        "reachable": False,
        "started_app": False,
        "started_serve": False,
        "pulled_model": False,
        "model": (model or os.environ.get("NEWTON3_OLLAMA_MODEL") or os.environ.get("NEWTON3_LLM_MODEL") or "llama3.2").strip(),
        "host": _ollama_host(),
    }

    if not _should_manage_ollama():
        out["skipped"] = "llm_auto_disabled_or_remote_backend"
        return out

    out["enabled"] = True
    host = out["host"]

    if ollama_reachable(host=host):
        out["reachable"] = True
        if pull_model:
            if verbose:
                print(f"[newton3] Pulling Ollama model {out['model']!r}…", file=sys.stderr)
            out["pulled_model"] = _pull_model(out["model"])
        return out

    if verbose:
        print("[newton3] Ollama not reachable — trying to start it…", file=sys.stderr)

    if _open_ollama_app_macos():
        out["started_app"] = True
        if verbose:
            print("[newton3] Opened Ollama.app (macOS); waiting for API…", file=sys.stderr)
    elif _start_ollama_serve():
        out["started_serve"] = True
        if verbose:
            print("[newton3] Started `ollama serve` in the background…", file=sys.stderr)
    else:
        out["error"] = (
            "Ollama is not running. Install from https://ollama.com/download or run: "
            "./scripts/setup_local_llm.sh install-ollama && ./scripts/setup_local_llm.sh native"
        )
        if verbose:
            print(f"[newton3] {out['error']}", file=sys.stderr)
        return out

    if _wait_for_ollama(host=host, port=_DEFAULT_PORT, timeout_sec=wait_timeout_sec):
        out["reachable"] = True
        if verbose:
            print(f"[newton3] Ollama ready at {host}:{_DEFAULT_PORT}", file=sys.stderr)
        if pull_model:
            if verbose:
                print(f"[newton3] Pulling model {out['model']!r} (first run may take minutes)…", file=sys.stderr)
            out["pulled_model"] = _pull_model(out["model"])
        return out

    out["error"] = (
        f"Ollama did not respond within {int(wait_timeout_sec)}s. "
        "Open the Ollama app or run `ollama serve` in another terminal."
    )
    if verbose:
        print(f"[newton3] {out['error']}", file=sys.stderr)
    return out
