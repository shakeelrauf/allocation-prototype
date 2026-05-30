"""Run API + UI locally: SQLite file under ./data by default.

React UI (separate dev server): ``cd ui && npm install && npm run dev`` — Vite
proxies ``/api`` to this server (default :8765). Build for production: ``cd ui
&& npm run build``; FastAPI serves ``ui/dist`` when present, otherwise ``static/``.
The React app uses client-side routes (e.g. ``/dashboard``, ``/events``); deep links
need the built SPA (``html=True`` static mount).

By default this script **starts Ollama automatically** if it is not already running
(macOS: opens Ollama.app; otherwise ``ollama serve`` in the background). The API then
auto-detects ``http://127.0.0.1:11434`` for Explain & AI. Use ``--no-ollama`` to skip,
``--ollama-pull`` to pull the default model on startup (slow first time).

Manual setup: ``./scripts/setup_local_llm.sh native`` or ``docker compose up`` (full stack).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Newton 3.0 local server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite path (sets NEWTON3_DB_PATH); default: ./data/newton3.db",
    )
    parser.add_argument("--reload", action="store_true", help="Dev auto-reload")
    parser.add_argument(
        "--with-ollama",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Probe/start local Ollama before the API (default: on)",
    )
    parser.add_argument(
        "--ollama-pull",
        action="store_true",
        help="Run `ollama pull` for NEWTON3_LLM_MODEL / llama3.2 after Ollama is up",
    )
    args = parser.parse_args()

    if args.db:
        os.environ["NEWTON3_DB_PATH"] = str(Path(args.db).expanduser().resolve())
    elif not os.environ.get("NEWTON3_DB_PATH"):
        from newton3.persistence.sqlite_store import default_sqlite_path

        os.environ["NEWTON3_DB_PATH"] = str(default_sqlite_path().resolve())

    if args.with_ollama:
        from newton3.local_ollama import ensure_ollama_running

        ensure_ollama_running(pull_model=args.ollama_pull)

    try:
        import uvicorn
    except ImportError as e:
        raise SystemExit(
            "Install uvicorn: pip install uvicorn[standard]"
        ) from e

    target = "newton3.api.app:app"
    if args.reload:
        uvicorn.run(target, host=args.host, port=args.port, reload=True, factory=False)
    else:
        from newton3.api.app import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
