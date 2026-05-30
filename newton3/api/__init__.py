"""HTTP API (FastAPI) — local Uvicorn and AWS Mangum console."""

from newton3.api.app import create_app

__all__ = ["create_app"]
