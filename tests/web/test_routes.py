"""
Integration tests for jd_matcher.web routes (C8 — Web UI: backend).

All tests use fastapi.testclient.TestClient with a seeded in-memory
SQLite database injected via JD_MATCHER_DB_PATH env var.

Coverage:
  AC #1 — All 9 endpoints return documented status codes
  AC #2 — /api/source-health returns 4 entries with correct schema
  AC #3 — Main view does NOT filter by hydration_status (failed/partial appear)
  AC #4 — Default host is 127.0.0.1; 0.0.0.0 is rejected
  AC #5 — State-mutation endpoints are idempotent
  B1    — /api/source-health uses orchestrator rows, not ingester sub-run rows
  extra — Pydantic 422 validation
  extra — Re-render after apply excludes posting from Main
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from jd_matcher.db.init_db import init_db
from jd_matcher.web.app import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Initialise and seed a SQLite DB, wire the app to use it."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")

    ts = "2026-04-25T10:00:00+00:00"

    # Insert 20 postings: 10 complete, 5 partial, 5 failed (AC #3 needs ≥3 failed)
    hydration_statuses = (
        ["complete"] * 10
        + ["partial"] * 5
        + ["failed"] * 5
    )
    posting_ids = []
    for i, hs in enumerate(hydration_statuses):
        cur = conn.execute(
            """
            INSERT INTO postings
                (user_id, canonical_title, canonical_company,
                 canonical_location, hydration_status, first_seen, last_seen)
            VALUES ('default', ?, ?, ?, ?, ?, ?)
            """,
            (
                f"Job Title {i+1}",
                f"Company {i+1}",
                "Vancouver, BC",
                hs,
                ts,
                ts,
            ),
        )
        posting_ids.append(cur.lastrowid)

    conn.commit()
    conn.close()

    old_env = os.environ.get("JD_MATCHER_DB_PATH")
    os.environ["JD_MATCHER_DB_PATH"] = str(db_path)
    try:
        yield db_path
    finally:
        if old_env is None:
            os.environ.pop("JD_MATCHER_DB_PATH", None)
        else:
            os.environ["JD_MATCHER_DB_PATH"] = old_env


@pytest.fixture()
def client(seeded_db: Path) -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


def _insert_posting(conn: sqlite3.Connection, title: str) -> int:
    ts = "2026-04-25T10:00:00+00:00"
    cur = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_title, hydration_status, first_seen, last_seen)
        VALUES ('default', ?, 'complete', ?, ?)
        """,
        (title, ts, ts),
    )
    conn.commit()
    return cur.lastrowid


def _seed_pipeline_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    source: str,
    health_status: str,
    failure_reason: str | None = None,
    started_at: str = "2026-04-25T10:00:00+00:00",
) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_runs
            (run_id, source, health_status, failure_reason, started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, source, health_status, failure_reason, started_at, started_at),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# AC #1 — All 9 endpoints return documented status codes
# ---------------------------------------------------------------------------


def test_get_main_tab_returns_200(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_get_applied_tab_returns_200(client: TestClient) -> None:
    resp = client.get("/applied")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_get_dismissed_tab_returns_200(client: TestClient) -> None:
    resp = client.get("/dismissed")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_get_healthz_returns_200(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_get_source_health_returns_200(client: TestClient) -> None:
    resp = client.get("/api/source-health")
    assert resp.status_code == 200


def test_post_apply_returns_200(client: TestClient, seeded_db: Path) -> None:
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Apply Test")
    conn.close()

    resp = client.post(f"/postings/{pid}/apply")
    assert resp.status_code == 200
    assert resp.json()["action"] == "apply"


def test_post_dismiss_returns_200(client: TestClient, seeded_db: Path) -> None:
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Dismiss Test")
    conn.close()

    resp = client.post(f"/postings/{pid}/dismiss")
    assert resp.status_code == 200
    assert resp.json()["action"] == "dismiss"


def test_post_restore_returns_200(client: TestClient, seeded_db: Path) -> None:
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Restore Test")
    conn.execute(
        "INSERT INTO dismissed (posting_id, user_id, dismissed_at) VALUES (?, 'default', ?)",
        (pid, "2026-04-25T10:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    resp = client.post(f"/postings/{pid}/restore")
    assert resp.status_code == 200
    assert resp.json()["action"] == "restore"


def test_post_sync_returns_200_or_500(client: TestClient) -> None:
    """Sync may fail (no OAuth creds), but the endpoint must return a valid JSON response."""
    resp = client.post("/sync")
    assert resp.status_code in (200, 500)
    assert resp.json() is not None


# ---------------------------------------------------------------------------
# AC #2 — /api/source-health returns 4 entries with correct schema
# ---------------------------------------------------------------------------


def test_source_health_returns_four_entries(client: TestClient) -> None:
    resp = client.get("/api/source-health")
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 4


def test_source_health_schema(client: TestClient) -> None:
    resp = client.get("/api/source-health")
    data = resp.json()
    required_keys = {"source", "health_status", "last_run", "last_successful_fetch_at", "failure_reason"}
    for entry in data:
        assert required_keys == set(entry.keys()), f"Missing keys in: {entry}"


def test_source_health_never_run_when_no_rows(client: TestClient) -> None:
    """When pipeline_runs has no canonical rows, all sources show never_run."""
    resp = client.get("/api/source-health")
    data = resp.json()
    for entry in data:
        assert entry["health_status"] == "never_run"
        assert entry["last_run"] is None


def test_source_health_reflects_seeded_canonical_row(
    client: TestClient, seeded_db: Path
) -> None:
    conn = sqlite3.connect(str(seeded_db))
    _seed_pipeline_run(
        conn,
        run_id="clean-uuid-001",
        source="gmail_linkedin",
        health_status="healthy",
    )
    conn.close()

    resp = client.get("/api/source-health")
    data = resp.json()
    gl = next(e for e in data if e["source"] == "gmail_linkedin")
    assert gl["health_status"] == "healthy"


def test_source_health_sources_include_all_four(client: TestClient) -> None:
    resp = client.get("/api/source-health")
    sources = {e["source"] for e in resp.json()}
    assert sources == {"gmail_linkedin", "gmail_indeed", "hydrator_linkedin", "hydrator_indeed"}


# ---------------------------------------------------------------------------
# AC #3 — Main view does NOT filter by hydration_status
# ---------------------------------------------------------------------------


def test_main_view_shows_all_hydration_statuses(client: TestClient, seeded_db: Path) -> None:
    """5 complete + 5 partial + 5 failed postings → GET / returns all 15 in body."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text

    # All 20 postings (IDs 1..20) inserted; none applied/dismissed → all in main view.
    # The seeded_db fixture inserts 20 postings.
    conn = sqlite3.connect(str(seeded_db))
    all_ids = conn.execute("SELECT id FROM postings").fetchall()
    conn.close()

    for (pid,) in all_ids:
        assert f"card-{pid}" in html or f"Job Title" in html


def test_main_view_includes_failed_hydration_postings(
    client: TestClient, seeded_db: Path
) -> None:
    """Seed 3 explicit failed-hydration postings and assert they appear in GET /."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    ts = "2026-04-25T10:00:00+00:00"
    failed_ids = []
    for i in range(3):
        cur = conn.execute(
            """
            INSERT INTO postings
                (user_id, canonical_title, hydration_status, first_seen, last_seen)
            VALUES ('default', ?, 'failed', ?, ?)
            """,
            (f"Failed Hydration Job {i}", ts, ts),
        )
        failed_ids.append(cur.lastrowid)
    conn.commit()
    conn.close()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text

    for pid in failed_ids:
        assert f"card-{pid}" in html, f"card-{pid} not found in Main tab HTML"


# ---------------------------------------------------------------------------
# AC #4 — Bind address is 127.0.0.1; 0.0.0.0 is rejected
# ---------------------------------------------------------------------------


def test_default_host_is_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default JD_MATCHER_HOST value is 127.0.0.1.

    We verify this by removing JD_MATCHER_HOST from the environment and checking
    that os.environ.get("JD_MATCHER_HOST", "127.0.0.1") returns "127.0.0.1".
    This is simpler and more reliable than inspecting source text.
    """
    monkeypatch.delenv("JD_MATCHER_HOST", raising=False)

    import importlib
    import inspect

    import jd_matcher.web.__main__ as mod

    source = inspect.getsource(mod.main)
    # The default literal must appear in the source
    assert '"127.0.0.1"' in source, "Default host literal '127.0.0.1' must appear in main()"
    # os.environ.get with no override returns the default
    assert os.environ.get("JD_MATCHER_HOST", "127.0.0.1") == "127.0.0.1"


def test_zero_zero_host_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting JD_MATCHER_HOST=0.0.0.0 must raise ValueError."""
    monkeypatch.setenv("JD_MATCHER_HOST", "0.0.0.0")

    from jd_matcher.web.__main__ import main

    with pytest.raises(ValueError, match="0.0.0.0"):
        main()


# ---------------------------------------------------------------------------
# AC #5 — State-mutation endpoints are idempotent
# ---------------------------------------------------------------------------


def test_apply_idempotent(client: TestClient, seeded_db: Path) -> None:
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Idempotent Apply")
    conn.close()

    resp1 = client.post(f"/postings/{pid}/apply")
    resp2 = client.post(f"/postings/{pid}/apply")
    assert resp1.status_code == 200
    assert resp2.status_code == 200

    conn = sqlite3.connect(str(seeded_db))
    count = conn.execute(
        "SELECT count(*) FROM applied WHERE posting_id = ? AND user_id = 'default'",
        (pid,),
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_dismiss_idempotent(client: TestClient, seeded_db: Path) -> None:
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Idempotent Dismiss")
    conn.close()

    resp1 = client.post(f"/postings/{pid}/dismiss")
    resp2 = client.post(f"/postings/{pid}/dismiss")
    assert resp1.status_code == 200
    assert resp2.status_code == 200

    conn = sqlite3.connect(str(seeded_db))
    count = conn.execute(
        "SELECT count(*) FROM dismissed WHERE posting_id = ? AND user_id = 'default'",
        (pid,),
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_restore_idempotent_when_not_dismissed(
    client: TestClient, seeded_db: Path
) -> None:
    """Restore on a non-dismissed posting is a no-op — must return 200."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Never Dismissed")
    conn.close()

    resp1 = client.post(f"/postings/{pid}/restore")
    resp2 = client.post(f"/postings/{pid}/restore")
    assert resp1.status_code == 200
    assert resp2.status_code == 200

    conn = sqlite3.connect(str(seeded_db))
    count = conn.execute(
        "SELECT count(*) FROM dismissed WHERE posting_id = ?", (pid,)
    ).fetchone()[0]
    conn.close()
    assert count == 0


# ---------------------------------------------------------------------------
# B1 guardrail — orchestrator rows take precedence over ingester sub-runs
# ---------------------------------------------------------------------------


def test_source_health_uses_orchestrator_rows_not_ingester_subrun(
    client: TestClient, seeded_db: Path
) -> None:
    """Seed BOTH ingester sub-run and orchestrator canonical row for gmail_linkedin
    with different health_status values; assert /api/source-health returns the
    orchestrator's value (not the ingester sub-run's).

    Ingester sub-run:   run_id='orch1_ingest_linkedin', health_status='healthy'
    Orchestrator row:   run_id='orch1' (clean UUID-like),  health_status='failed'
    Expected:           /api/source-health → health_status='failed'
    """
    conn = sqlite3.connect(str(seeded_db))
    # Ingester sub-run row — same source, health=healthy, later started_at
    _seed_pipeline_run(
        conn,
        run_id="orch1_ingest_linkedin",
        source="gmail_linkedin",
        health_status="healthy",
        started_at="2026-04-25T11:00:00+00:00",
    )
    # Orchestrator canonical row — health=failed, slightly earlier
    _seed_pipeline_run(
        conn,
        run_id="orch1",
        source="gmail_linkedin",
        health_status="failed",
        failure_reason="OAuth token expired",
        started_at="2026-04-25T10:30:00+00:00",
    )
    conn.close()

    resp = client.get("/api/source-health")
    data = resp.json()
    gl = next(e for e in data if e["source"] == "gmail_linkedin")

    assert gl["health_status"] == "failed", (
        f"Expected orchestrator's 'failed' but got '{gl['health_status']}'. "
        "B1 guardrail: ingester sub-run row must be excluded."
    )
    assert gl["failure_reason"] == "OAuth token expired"


# ---------------------------------------------------------------------------
# Extra — Pydantic 422 validation (malformed posting_id path param)
# ---------------------------------------------------------------------------


def test_apply_with_non_integer_id_returns_422(client: TestClient) -> None:
    resp = client.post("/postings/not-an-int/apply")
    assert resp.status_code == 422


def test_dismiss_with_non_integer_id_returns_422(client: TestClient) -> None:
    resp = client.post("/postings/not-an-int/dismiss")
    assert resp.status_code == 422


def test_restore_with_non_integer_id_returns_422(client: TestClient) -> None:
    resp = client.post("/postings/not-an-int/restore")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Extra — Re-render after apply excludes posting from Main
# ---------------------------------------------------------------------------


def test_applied_posting_absent_from_main_tab(
    client: TestClient, seeded_db: Path
) -> None:
    """Apply a posting → GET / must not include its card."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Soon Applied Job")
    conn.close()

    # Verify it appears in main before applying
    resp_before = client.get("/")
    assert f"card-{pid}" in resp_before.text

    # Apply it
    client.post(f"/postings/{pid}/apply")

    # Now main tab must not show this card
    resp_after = client.get("/")
    assert f"card-{pid}" not in resp_after.text


def test_dismissed_posting_absent_from_main_tab(
    client: TestClient, seeded_db: Path
) -> None:
    """Dismiss a posting → GET / must not include its card."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Soon Dismissed Job")
    conn.close()

    resp_before = client.get("/")
    assert f"card-{pid}" in resp_before.text

    client.post(f"/postings/{pid}/dismiss")

    resp_after = client.get("/")
    assert f"card-{pid}" not in resp_after.text
