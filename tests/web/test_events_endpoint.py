"""
Tests for POST /api/events (C10 — Events instrumentation) — TASK-M1-010 AC #7.

Coverage:
  AC #7 (a) — endpoint writes exactly one row per call
  AC #7 (b) — correct event_type stored
  AC #7 (c) — metadata serialized as JSON string
  AC #7 (d) — session_id stored
  AC #7 (e) — invalid event_type rejected (422)
  TDD §C10 quality (e) — DB-write failure → 204 + WARNING logged, never 500
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Generator
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from jd_matcher.db.init_db import init_db
from jd_matcher.web.app import app

TS = "2026-04-25T10:00:00+00:00"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_db(tmp_path: Path) -> Generator[Path, None, None]:
    db_path = tmp_path / "test_events.db"
    init_db(db_path)
    # seed one posting so posting_id FK can be set
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_title, hydration_status, first_seen, last_seen)
        VALUES ('default', 'Test Job', 'complete', ?, ?)
        """,
        (TS, TS),
    )
    conn.commit()
    conn.close()

    old = os.environ.get("JD_MATCHER_DB_PATH")
    os.environ["JD_MATCHER_DB_PATH"] = str(db_path)
    try:
        yield db_path
    finally:
        if old is None:
            os.environ.pop("JD_MATCHER_DB_PATH", None)
        else:
            os.environ["JD_MATCHER_DB_PATH"] = old


@pytest.fixture()
def client(seeded_db: Path) -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


def _count_events(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT count(*) FROM events").fetchone()[0]
    conn.close()
    return count


def _last_event(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        """
        SELECT session_id, event_type, posting_id, metadata, timestamp
        FROM events ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    conn.close()
    return {
        "session_id": row[0],
        "event_type": row[1],
        "posting_id": row[2],
        "metadata": row[3],
        "timestamp": row[4],
    }


# ---------------------------------------------------------------------------
# AC #7 (a) — one row written per call
# ---------------------------------------------------------------------------


def test_event_write_inserts_one_row(client: TestClient, seeded_db: Path) -> None:
    before = _count_events(seeded_db)
    resp = client.post(
        "/api/events",
        json={"event_type": "card_viewed", "posting_id": 1, "session_id": "sess-001"},
    )
    assert resp.status_code == 204
    after = _count_events(seeded_db)
    assert after == before + 1


def test_multiple_events_write_multiple_rows(client: TestClient, seeded_db: Path) -> None:
    for etype in ["card_viewed", "card_expanded", "card_dismissed"]:
        client.post(
            "/api/events",
            json={"event_type": etype, "posting_id": 1, "session_id": "sess-002"},
        )
    assert _count_events(seeded_db) == 3


# ---------------------------------------------------------------------------
# AC #7 (b) — correct event_type stored
# ---------------------------------------------------------------------------


def test_event_type_stored_correctly(client: TestClient, seeded_db: Path) -> None:
    client.post(
        "/api/events",
        json={"event_type": "card_marked_applied", "posting_id": 1, "session_id": "sess-003"},
    )
    ev = _last_event(seeded_db)
    assert ev["event_type"] == "card_marked_applied"


# ---------------------------------------------------------------------------
# AC #7 (c) — metadata serialized as JSON string
# ---------------------------------------------------------------------------


def test_metadata_stored_as_json_string(client: TestClient, seeded_db: Path) -> None:
    meta = {"time_to_decide_ms": 4500, "session_id": "sess-004"}
    client.post(
        "/api/events",
        json={"event_type": "card_dismissed", "posting_id": 1, "metadata": meta, "session_id": "sess-004"},
    )
    ev = _last_event(seeded_db)
    assert ev["metadata"] is not None
    parsed = json.loads(ev["metadata"])
    assert parsed["time_to_decide_ms"] == 4500


def test_null_metadata_stored_as_null(client: TestClient, seeded_db: Path) -> None:
    client.post(
        "/api/events",
        json={"event_type": "session_start", "session_id": "sess-005"},
    )
    ev = _last_event(seeded_db)
    assert ev["metadata"] is None


# ---------------------------------------------------------------------------
# AC #7 (d) — session_id stored
# ---------------------------------------------------------------------------


def test_session_id_stored(client: TestClient, seeded_db: Path) -> None:
    client.post(
        "/api/events",
        json={"event_type": "tab_switched", "session_id": "my-session-xyz"},
    )
    ev = _last_event(seeded_db)
    assert ev["session_id"] == "my-session-xyz"


# ---------------------------------------------------------------------------
# AC #7 (e) — invalid event_type rejected with 422
# ---------------------------------------------------------------------------


def test_invalid_event_type_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/api/events",
        json={"event_type": "not_a_real_event", "session_id": "sess-x"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TDD §C10 quality (e) — DB-write failure returns 204 + logs warning (never 500)
# ---------------------------------------------------------------------------


def test_db_write_failure_returns_204_not_500(
    client: TestClient, seeded_db: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Mock the DB connection's execute to raise; assert 204 and WARNING logged."""
    import jd_matcher.web.routes as routes_module

    original_open = routes_module._open_conn

    def failing_open(db_path):
        conn = original_open(db_path)
        # Patch execute on the connection object to raise on INSERT into events
        real_execute = conn.execute

        def mock_execute(sql, *args, **kwargs):
            if "INSERT INTO events" in sql:
                raise sqlite3.OperationalError("simulated DB failure")
            return real_execute(sql, *args, **kwargs)

        conn.execute = mock_execute
        return conn

    with caplog.at_level(logging.WARNING, logger="jd_matcher.web.routes"):
        with mock.patch.object(routes_module, "_open_conn", side_effect=failing_open):
            resp = client.post(
                "/api/events",
                json={"event_type": "card_viewed", "posting_id": 1, "session_id": "sess-fail"},
            )

    assert resp.status_code == 204, (
        f"DB failure must return 204 (best-effort), got {resp.status_code}"
    )
    assert any(
        "Event write failed" in r.message or "simulated DB failure" in r.message
        for r in caplog.records
    ), "Expected WARNING log for DB failure but none found"


# ---------------------------------------------------------------------------
# All M1 active event types are accepted (smoke)
# ---------------------------------------------------------------------------


M1_EVENT_TYPES = [
    "card_viewed",
    "card_expanded",
    "card_dismissed",
    "card_marked_applied",
    "sync_triggered",
    "sync_completed",
    "tab_switched",
    "card_restored",
    "session_start",
    "session_end",
    "source_failure",
]


@pytest.mark.parametrize("etype", M1_EVENT_TYPES)
def test_all_m1_event_types_accepted(client: TestClient, etype: str) -> None:
    resp = client.post(
        "/api/events",
        json={"event_type": etype, "session_id": "sess-smoke"},
    )
    assert resp.status_code == 204, f"event_type={etype!r} was rejected with {resp.status_code}"
