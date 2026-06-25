"""Pytest configuration — use development mode for unit tests."""

import os

os.environ.setdefault("APP_ENV", "development")
