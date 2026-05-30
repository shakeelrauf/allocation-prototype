"""Repository root paths (fixtures, UI dist, SQLite default dir)."""

from __future__ import annotations

from pathlib import Path

# newton3/paths.py → package dir → repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
