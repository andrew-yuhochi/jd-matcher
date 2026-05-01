"""
Shared pytest configuration for jd-matcher.

Exposes:
  empty_db      — pytest fixture: yields (conn, db_path) for a fresh tmp SQLite
  seed_posting  — plain function: inserts a posting; also re-exported from helpers
  seed_canonical — plain function: inserts posting + canonical + link; also re-exported

The plain functions live in tests/helpers.py so they can be imported directly
by test modules (conftest.py is auto-loaded by pytest but not importable by name).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jd_matcher.db.init_db import init_db
from tests.helpers import seed_canonical, seed_posting  # noqa: F401 — re-export


@pytest.fixture()
def empty_db(tmp_path: Path):
    """Yield (conn, db_path) for a fresh SQLite DB with init_db applied.

    Foreign keys are enabled. The connection is closed after the test.
    """
    import sqlite3

    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn, db_path
    finally:
        conn.close()
