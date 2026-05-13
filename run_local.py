"""Run API + UI locally: SQLite file under ./data by default.

React UI (separate dev server): ``cd ui && npm install && npm run dev`` — Vite
proxies ``/api`` to this server (default :8765). Build for production: ``cd ui
&& npm run build``; FastAPI serves ``ui/dist`` when present, otherwise ``static/``.
The React app uses client-side routes (e.g. ``/dashboard``, ``/events``); deep links
need the built SPA (``html=True`` static mount).

Ollama (optional): no Docker on Mac — ``./scripts/setup_local_llm.sh install-ollama`` then
``native``; or use ``docker`` if you have Docker; then
``python -m cli local-llm`` to print ``NEWTON3_LLM_*`` exports. Or set
``NEWTON3_LLM_URL`` / ``NEWTON3_LLM_MODEL`` manually (see ``llm_explain`` docstring).
Without Ollama (or auto-detect), allocation narrative falls back to template-only text.
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
    args = parser.parse_args()

    if args.db:
        os.environ["NEWTON3_DB_PATH"] = str(Path(args.db).expanduser().resolve())
    elif not os.environ.get("NEWTON3_DB_PATH"):
        from sqlite_store import default_sqlite_path

        os.environ["NEWTON3_DB_PATH"] = str(default_sqlite_path().resolve())

    try:
        import uvicorn
    except ImportError as e:
        raise SystemExit(
            "Install uvicorn: pip install uvicorn[standard]"
        ) from e

    target = "api:app"
    if args.reload:
        uvicorn.run(target, host=args.host, port=args.port, reload=True)
    else:
        from api import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
