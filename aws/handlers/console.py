"""Full FastAPI console API on Lambda via Mangum (DynamoDB store)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("NEWTON3_STORE", "dynamodb")
os.environ.setdefault("NEWTON3_STACK", "aws-sam")
os.environ.setdefault("NEWTON3_LLM_AUTO", "0")

from mangum import Mangum  # noqa: E402

from newton3.api.app import create_app  # noqa: E402
from newton3.persistence.store_factory import make_store  # noqa: E402

_asgi_app = None


def _asgi():
    global _asgi_app
    if _asgi_app is None:
        _asgi_app = create_app(make_store())
    return _asgi_app


def _api_base_path() -> str:
    stage = (os.environ.get("NEWTON3_API_STAGE") or os.environ.get("STAGE") or "").strip()
    return f"/{stage}" if stage else "/"


handler = Mangum(_asgi(), lifespan="off", api_gateway_base_path=_api_base_path())
