"""Lightweight structured hooks (stdlib logging)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

_log = logging.getLogger("newton3")
if not _log.handlers:
    _h = logging.StreamHandler()
    _log.addHandler(_h)
_log.setLevel(logging.INFO)


def emit(event: str, **fields: Any) -> None:
    """Structured observability hook (grep logs or ship to your collector)."""
    if os.environ.get("NEWTON3_LOG_JSON"):
        _log.info(json.dumps({"event": event, **fields}, default=str))
    else:
        _log.info("%s %s", event, fields)
