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
from unittest import mock

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


def test_post_sync_returns_pipeline_summary(client: TestClient) -> None:
    """POST /sync with a mocked run_pipeline returns 200 and the documented response shape."""
    from datetime import timezone

    from jd_matcher.pipeline import PipelineRunSummary, SourceResult

    fake_summary = PipelineRunSummary(
        run_id="test-run-123",
        started_at=datetime(2026, 4, 25, 10, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 4, 25, 10, 0, 5, tzinfo=timezone.utc),
        sources=[
            SourceResult(
                source="gmail_linkedin",
                health_status="healthy",
                new_postings=3,
                failure_reason=None,
            )
        ],
        steps=["ingest", "hydrate"],
        total_new_postings=3,
    )

    with mock.patch("jd_matcher.pipeline.run_pipeline", return_value=fake_summary):
        resp = client.post("/sync")

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "test-run-123"
    assert body["total_new_postings"] == 3
    assert body["failed_sources"] == []
    assert "started_at" in body
    assert "finished_at" in body


def test_post_sync_skip_live_no_credentials_needed(client: TestClient) -> None:
    """POST /sync with SKIP_LIVE=1 skips OAuth loading and calls run_pipeline(credentials=None)."""
    from jd_matcher.pipeline import PipelineRunSummary, SourceResult

    fake_summary = PipelineRunSummary(
        run_id="skip-live-run",
        started_at=datetime(2026, 4, 25, 10, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 4, 25, 10, 0, 5, tzinfo=timezone.utc),
        sources=[],
        steps=[],
        total_new_postings=0,
    )

    with (
        mock.patch.dict(os.environ, {"SKIP_LIVE": "1"}),
        mock.patch("jd_matcher.pipeline.run_pipeline", return_value=fake_summary) as mock_run,
    ):
        resp = client.post("/sync")

    assert resp.status_code == 200
    # Confirm run_pipeline was called with credentials=None (no OAuth attempted)
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs.get("credentials") is None


def test_post_sync_missing_client_secrets_returns_503(
    seeded_db: Path, tmp_path: Path
) -> None:
    """POST /sync without SKIP_LIVE and without credentials.json → 503."""
    missing_path = tmp_path / "nonexistent_credentials.json"
    with (
        mock.patch.dict(
            os.environ,
            {"SKIP_LIVE": "0", "GMAIL_OAUTH_CLIENT_PATH": str(missing_path)},
        ),
    ):
        test_client = TestClient(app, raise_server_exceptions=True)
        resp = test_client.post("/sync")

    assert resp.status_code == 503
    body = resp.json()
    assert "OAuth client secrets not found" in body["error"]


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
        assert f"card-{pid}" in html, f"card-{pid} not found in Main tab HTML"


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
    """Patching uvicorn.run and invoking main() proves the production call uses host='127.0.0.1'."""
    monkeypatch.delenv("JD_MATCHER_HOST", raising=False)
    monkeypatch.delenv("JD_MATCHER_PORT", raising=False)

    with mock.patch("uvicorn.run") as mock_run:
        from jd_matcher.web.__main__ import main
        main()
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        assert kwargs.get("host") == "127.0.0.1", (
            f"Expected host='127.0.0.1' but uvicorn.run was called with host={kwargs.get('host')!r}"
        )
        assert kwargs.get("port") == 8765, (
            f"Expected port=8765 but uvicorn.run was called with port={kwargs.get('port')!r}"
        )


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


def test_source_health_carry_forward_last_successful_fetch_at(
    client: TestClient, seeded_db: Path
) -> None:
    """When the latest run is failed, last_successful_fetch_at carries the prior healthy row's timestamp."""
    conn = sqlite3.connect(str(seeded_db))
    # T1: healthy run
    _seed_pipeline_run(
        conn,
        run_id="healthy-run-001",
        source="gmail_linkedin",
        health_status="healthy",
        started_at="2026-04-20T10:00:00+00:00",
    )
    # T2: failed run (most recent)
    _seed_pipeline_run(
        conn,
        run_id="failed-run-002",
        source="gmail_linkedin",
        health_status="failed",
        failure_reason="OAuth token expired",
        started_at="2026-04-25T10:00:00+00:00",
    )
    conn.close()

    resp = client.get("/api/source-health")
    data = resp.json()
    gl = next(e for e in data if e["source"] == "gmail_linkedin")

    assert gl["health_status"] == "failed"
    assert gl["last_successful_fetch_at"] is not None, (
        "last_successful_fetch_at must carry forward the T1 healthy timestamp, not be null"
    )
    assert "2026-04-20" in gl["last_successful_fetch_at"], (
        f"Expected T1 timestamp (2026-04-20) but got {gl['last_successful_fetch_at']!r}"
    )


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


# ---------------------------------------------------------------------------
# full_jd pass-through — Main, Applied, Dismissed tabs
# ---------------------------------------------------------------------------


def _insert_posting_with_jd(conn: sqlite3.Connection, title: str, full_jd: str) -> int:
    ts = "2026-04-25T10:00:00+00:00"
    cur = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_title, hydration_status, first_seen, last_seen, full_jd)
        VALUES ('default', ?, 'complete', ?, ?, ?)
        """,
        (title, ts, ts, full_jd),
    )
    conn.commit()
    return cur.lastrowid


def test_main_tab_renders_full_jd_text(client: TestClient, seeded_db: Path) -> None:
    """GET / with a posting that has full_jd set must render the JD text, not the fallback."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    jd_text = "Unique JD content for main tab test: looking for Python engineers."
    pid = _insert_posting_with_jd(conn, "Main JD Job", jd_text)
    conn.close()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert jd_text in html, "full_jd text must appear in Main tab HTML"
    assert f"card-{pid}" in html


def test_applied_tab_renders_full_jd_text(client: TestClient, seeded_db: Path) -> None:
    """GET /applied with an applied posting that has full_jd must render the JD text."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    jd_text = "Unique JD content for applied tab test: senior ML role."
    pid = _insert_posting_with_jd(conn, "Applied JD Job", jd_text)
    ts = "2026-04-25T10:00:00+00:00"
    conn.execute(
        "INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at) VALUES (?, 'default', 'Applied', ?, ?)",
        (pid, ts, ts),
    )
    conn.commit()
    conn.close()

    resp = client.get("/applied")
    assert resp.status_code == 200
    html = resp.text
    assert jd_text in html, "full_jd text must appear in Applied tab HTML"


def test_dismissed_tab_renders_full_jd_text(client: TestClient, seeded_db: Path) -> None:
    """GET /dismissed with a dismissed posting that has full_jd must render the JD text."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    jd_text = "Unique JD content for dismissed tab test: data scientist wanted."
    pid = _insert_posting_with_jd(conn, "Dismissed JD Job", jd_text)
    ts = "2026-04-25T10:00:00+00:00"
    conn.execute(
        "INSERT INTO dismissed (posting_id, user_id, dismissed_at) VALUES (?, 'default', ?)",
        (pid, ts),
    )
    conn.commit()
    conn.close()

    resp = client.get("/dismissed")
    assert resp.status_code == 200
    html = resp.text
    assert jd_text in html, "full_jd text must appear in Dismissed tab HTML"


# ---------------------------------------------------------------------------
# Bug 2 — Applied/Dismissed cards must use card-expanded-body (not card-body)
# ---------------------------------------------------------------------------


def test_applied_tab_jd_wrapped_in_card_expanded_body(
    client: TestClient, seeded_db: Path
) -> None:
    """Applied tab: full_jd must be inside .card-expanded-body, not .card-body."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    jd_text = "Applied expand-body sentinel JD text."
    pid = _insert_posting_with_jd(conn, "Applied Expand Job", jd_text)
    ts = "2026-04-25T10:00:00+00:00"
    conn.execute(
        "INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at) VALUES (?, 'default', 'Applied', ?, ?)",
        (pid, ts, ts),
    )
    conn.commit()
    conn.close()

    resp = client.get("/applied")
    assert resp.status_code == 200
    html = resp.text

    # card-expanded-body must be present for applied cards
    assert "card-expanded-body" in html, "Applied cards must use card-expanded-body"
    # card-body must NOT be used (old incorrect class)
    assert 'class="card-body"' not in html, "Applied cards must NOT use card-body"
    # The JD text must appear inside a card-expanded-body section
    expanded_body_idx = html.find("card-expanded-body")
    jd_idx = html.find(jd_text)
    assert expanded_body_idx != -1 and jd_idx > expanded_body_idx, (
        "full_jd must appear after card-expanded-body open tag"
    )


def test_dismissed_tab_jd_wrapped_in_card_expanded_body(
    client: TestClient, seeded_db: Path
) -> None:
    """Dismissed tab: full_jd must be inside .card-expanded-body, not .card-body."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    jd_text = "Dismissed expand-body sentinel JD text."
    pid = _insert_posting_with_jd(conn, "Dismissed Expand Job", jd_text)
    ts = "2026-04-25T10:00:00+00:00"
    conn.execute(
        "INSERT INTO dismissed (posting_id, user_id, dismissed_at) VALUES (?, 'default', ?)",
        (pid, ts),
    )
    conn.commit()
    conn.close()

    resp = client.get("/dismissed")
    assert resp.status_code == 200
    html = resp.text

    assert "card-expanded-body" in html, "Dismissed cards must use card-expanded-body"
    assert 'class="card-body"' not in html, "Dismissed cards must NOT use card-body"
    expanded_body_idx = html.find("card-expanded-body")
    jd_idx = html.find(jd_text)
    assert expanded_body_idx != -1 and jd_idx > expanded_body_idx, (
        "full_jd must appear after card-expanded-body open tag"
    )


def test_main_tab_jd_not_rendered_outside_no_html_in_plain_text(
    client: TestClient, seeded_db: Path
) -> None:
    """GET / with plain-text full_jd must not contain literal HTML angle brackets."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    plain_jd = "Plain text JD with no tags."
    _insert_posting_with_jd(conn, "Plain JD Job", plain_jd)
    conn.close()

    resp = client.get("/")
    html = resp.text
    # The plain_jd text should appear but NOT as a literal HTML tag sequence
    assert plain_jd in html
    # Verify the rendered card-expanded-body section does not contain raw <p> or <ul> tags
    # that would come from unstripped HTML (Jinja escapes them to &lt; but we check the
    # source text doesn't have literal angle brackets from un-escaped HTML)
    assert "&lt;p&gt;" not in html, "HTML tags must not appear escaped in rendered output"


# ---------------------------------------------------------------------------
# JD rendering consistency — identical across Main / Applied / Dismissed tabs
# ---------------------------------------------------------------------------


def _setup_cross_tab_jd_posting(seeded_db: Path, full_jd: str) -> tuple[int, int, int]:
    """Seed one posting per tab (main, applied, dismissed) all with the same full_jd.

    Returns (pid_main, pid_applied, pid_dismissed).
    """
    ts = "2026-04-25T10:00:00+00:00"
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")

    def _ins(title: str) -> int:
        cur = conn.execute(
            """
            INSERT INTO postings
                (user_id, canonical_title, hydration_status, first_seen, last_seen, full_jd)
            VALUES ('default', ?, 'complete', ?, ?, ?)
            """,
            (title, ts, ts, full_jd),
        )
        return cur.lastrowid

    pid_main = _ins("Cross-tab JD Test — Main")
    pid_applied = _ins("Cross-tab JD Test — Applied")
    conn.execute(
        "INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at) VALUES (?, 'default', 'Applied', ?, ?)",
        (pid_applied, ts, ts),
    )
    pid_dismissed = _ins("Cross-tab JD Test — Dismissed")
    conn.execute(
        "INSERT INTO dismissed (posting_id, user_id, dismissed_at) VALUES (?, 'default', ?)",
        (pid_dismissed, ts),
    )
    conn.commit()
    conn.close()
    return pid_main, pid_applied, pid_dismissed


def _extract_card_expanded_body_html(html: str, pid: int) -> str:
    """Return the outer HTML of the .card-expanded-body div inside card-{pid}."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("article", id=f"card-{pid}")
    assert card is not None, f"card-{pid} not found in HTML"
    expanded = card.find("div", class_="card-expanded-body")
    assert expanded is not None, f"card-expanded-body not found inside card-{pid}"
    return str(expanded)


def _extract_card_dom_order(html: str, pid: int) -> list[tuple[str, list[str] | None]]:
    """Return list of (tag, classes) for direct children of card-{pid}."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("article", id=f"card-{pid}")
    assert card is not None, f"card-{pid} not found in HTML"
    return [
        (child.name, child.get("class"))
        for child in card.children
        if hasattr(child, "get")
    ]


@pytest.mark.parametrize(
    "full_jd",
    [
        "Short JD text.",
        "Multi-line JD:\nLine 1\nLine 2\nLine 3",
        "JD with  extra   spaces and\ttabs.",
    ],
    ids=["short", "multiline", "whitespace"],
)
def test_jd_expanded_body_identical_across_tabs(
    client: TestClient, seeded_db: Path, full_jd: str
) -> None:
    """Regression: .card-expanded-body inner HTML must be byte-identical across
    Main, Applied, and Dismissed tabs for the same full_jd content.

    Root cause fixed: Applied/Dismissed templates previously inlined the JD block
    with different indentation levels and card-actions ordering, causing structural
    inconsistency. Now all three tabs share _card_jd_body.html partial with
    card-actions always preceding card-expanded-body.
    """
    pid_main, pid_applied, pid_dismissed = _setup_cross_tab_jd_posting(seeded_db, full_jd)

    html_main = client.get("/").text
    html_applied = client.get("/applied").text
    html_dismissed = client.get("/dismissed").text

    body_main = _extract_card_expanded_body_html(html_main, pid_main)
    body_applied = _extract_card_expanded_body_html(html_applied, pid_applied)
    body_dismissed = _extract_card_expanded_body_html(html_dismissed, pid_dismissed)

    assert body_main == body_applied, (
        f"Main vs Applied card-expanded-body mismatch.\n"
        f"Main:    {body_main!r}\n"
        f"Applied: {body_applied!r}"
    )
    assert body_main == body_dismissed, (
        f"Main vs Dismissed card-expanded-body mismatch.\n"
        f"Main:      {body_main!r}\n"
        f"Dismissed: {body_dismissed!r}"
    )


# ---------------------------------------------------------------------------
# Un-apply endpoint
# ---------------------------------------------------------------------------


def test_post_unapply_returns_200(client: TestClient, seeded_db: Path) -> None:
    """POST /postings/{id}/unapply returns 200 with action='unapply'."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Unapply Test")
    ts = "2026-04-25T10:00:00+00:00"
    conn.execute(
        "INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at) "
        "VALUES (?, 'default', 'Applied', ?, ?)",
        (pid, ts, ts),
    )
    conn.commit()
    conn.close()

    resp = client.post(f"/postings/{pid}/unapply")
    assert resp.status_code == 200
    assert resp.json()["action"] == "unapply"


def test_unapply_removes_posting_from_applied(client: TestClient, seeded_db: Path) -> None:
    """After POST /unapply, the posting no longer appears in Applied tab."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Unapply Removal Test")
    ts = "2026-04-25T10:00:00+00:00"
    conn.execute(
        "INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at) "
        "VALUES (?, 'default', 'Applied', ?, ?)",
        (pid, ts, ts),
    )
    conn.commit()
    conn.close()

    # Verify appears in applied before unapply
    resp_before = client.get("/applied")
    assert f"card-{pid}" in resp_before.text

    client.post(f"/postings/{pid}/unapply")

    # Must no longer appear in applied tab
    resp_after = client.get("/applied")
    assert f"card-{pid}" not in resp_after.text


def test_unapply_with_non_integer_id_returns_422(client: TestClient) -> None:
    resp = client.post("/postings/not-an-int/unapply")
    assert resp.status_code == 422


def test_applied_template_renders_unapply_button(
    client: TestClient, seeded_db: Path
) -> None:
    """GET /applied with an applied posting must render the Unapply button."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Unapply Button Test")
    ts = "2026-04-25T10:00:00+00:00"
    conn.execute(
        "INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at) "
        "VALUES (?, 'default', 'Applied', ?, ?)",
        (pid, ts, ts),
    )
    conn.commit()
    conn.close()

    resp = client.get("/applied")
    assert resp.status_code == 200
    assert "btn-unapply" in resp.text


# ---------------------------------------------------------------------------
# Viewed / new sort (Feature 3)
# ---------------------------------------------------------------------------


def _insert_event_for_posting(
    conn: sqlite3.Connection, posting_id: int, event_type: str
) -> None:
    conn.execute(
        """
        INSERT INTO events (user_id, event_type, posting_id, timestamp)
        VALUES ('default', ?, ?, ?)
        """,
        (event_type, posting_id, "2026-04-25T12:00:00+00:00"),
    )
    conn.commit()


def test_viewed_posting_renders_with_card_viewed_class(
    client: TestClient, seeded_db: Path
) -> None:
    """A posting with a card_expanded event renders with class='card card-viewed'."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Viewed Posting")
    _insert_event_for_posting(conn, pid, "card_expanded")
    conn.close()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert f'id="card-{pid}"' in html
    # The card element for this posting must contain card-viewed class
    assert "card-viewed" in html


def test_unviewed_posting_renders_without_card_viewed_class_on_its_card(
    client: TestClient, seeded_db: Path
) -> None:
    """A posting with no card_expanded events must NOT have card-viewed on its card."""
    # Use a fresh DB with only one posting so we can isolate the card
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    # Apply all existing postings to clear the main view
    existing = conn.execute("SELECT id FROM postings").fetchall()
    ts = "2026-04-25T10:00:00+00:00"
    for (eid,) in existing:
        conn.execute(
            "INSERT OR IGNORE INTO applied (posting_id, user_id, status, applied_at, status_updated_at) "
            "VALUES (?, 'default', 'Applied', ?, ?)",
            (eid, ts, ts),
        )
    conn.commit()

    pid = _insert_posting(conn, "Unviewed Posting")
    # No card_expanded event for this posting
    conn.close()

    resp = client.get("/")
    html = resp.text
    assert f'id="card-{pid}"' in html
    # This specific card must NOT have card-viewed
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("article", id=f"card-{pid}")
    assert card is not None
    assert "card-viewed" not in (card.get("class") or [])


# ---------------------------------------------------------------------------
# (Original test suite continues below)
# ---------------------------------------------------------------------------


def test_card_dom_order_identical_across_tabs(
    client: TestClient, seeded_db: Path
) -> None:
    """The sequence of direct child div classes inside each card must be identical
    across all three tabs: card-line1, card-line2, card-line3, card-actions,
    card-expanded-body.

    This guards against structural drift that causes visual inconsistency even when
    the JD text content is identical (e.g. card-actions appearing after card-expanded-body
    on Dismissed changes layout due to CSS ordering).
    """
    full_jd = "DOM order test JD."
    pid_main, pid_applied, pid_dismissed = _setup_cross_tab_jd_posting(seeded_db, full_jd)

    html_main = client.get("/").text
    html_applied = client.get("/applied").text
    html_dismissed = client.get("/dismissed").text

    order_main = _extract_card_dom_order(html_main, pid_main)
    order_applied = _extract_card_dom_order(html_applied, pid_applied)
    order_dismissed = _extract_card_dom_order(html_dismissed, pid_dismissed)

    # card-actions must come before card-expanded-body in all tabs
    expected_tail = [["card-actions"], ["card-expanded-body"]]
    for tab_name, order in [("Main", order_main), ("Applied", order_applied), ("Dismissed", order_dismissed)]:
        div_classes = [c for _, c in order]
        assert div_classes[-2:] == expected_tail, (
            f"{tab_name} tab: last two divs must be card-actions then card-expanded-body.\n"
            f"Got: {div_classes}"
        )
