"""
Tests for the C3 email_ingest_log writer hook in GmailIngester (AC #2).

Verifies:
  - fetch_for_sender inserts one row per email with required metadata + 0 counters
  - INSERT OR IGNORE prevents duplicate rows when the same message is re-fetched
  - The canonical pipeline_run_id (not sub-run) is stored in the log row
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.ingest.gmail import GmailIngester


@pytest.fixture()
def test_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture()
def skip_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKIP_LIVE", "1")


def _count_log_rows(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM email_ingest_log").fetchone()[0]
    finally:
        conn.close()


def _get_log_rows(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT gmail_message_id, source, sender, subject, received_at,
                   ingested_at, pipeline_run_id,
                   urls_extracted_count, urls_new_count, postings_created_count,
                   postings_hydrated_count, postings_hydration_failed_count
            FROM email_ingest_log ORDER BY id
            """
        ).fetchall()
        cols = [
            "gmail_message_id", "source", "sender", "subject", "received_at",
            "ingested_at", "pipeline_run_id",
            "urls_extracted_count", "urls_new_count", "postings_created_count",
            "postings_hydrated_count", "postings_hydration_failed_count",
        ]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


class TestC3IngestLogWriter:
    def test_fetch_inserts_one_row_per_email(
        self, test_db: Path, skip_live: None
    ) -> None:
        """Each fetched email produces exactly one email_ingest_log row."""
        ingester = GmailIngester(credentials=None, db_path=test_db)
        emails = ingester.fetch_for_sender(
            "linkedin",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            run_id="sub-run-001",
            canonical_run_id="canonical-run-001",
        )
        assert len(emails) > 0, "No fixture emails found — check tests/fixtures/gmail/linkedin/"

        rows = _get_log_rows(test_db)
        assert len(rows) == len(emails), (
            f"Expected {len(emails)} email_ingest_log rows, got {len(rows)}"
        )

    def test_inserted_row_has_required_metadata(
        self, test_db: Path, skip_live: None
    ) -> None:
        """Inserted rows must have gmail_message_id, source, sender, subject, received_at, ingested_at, pipeline_run_id."""
        ingester = GmailIngester(credentials=None, db_path=test_db)
        ingester.fetch_for_sender(
            "linkedin",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            run_id="sub-run-002",
            canonical_run_id="canonical-run-002",
        )
        rows = _get_log_rows(test_db)
        assert rows, "No rows inserted"

        for row in rows:
            assert row["gmail_message_id"], "gmail_message_id must be non-empty"
            assert row["source"] == "linkedin", f"source mismatch: {row['source']}"
            assert row["sender"], "sender must be non-empty"
            assert row["subject"] is not None, "subject must not be None"
            assert row["received_at"], "received_at must be set"
            assert row["ingested_at"], "ingested_at must be set"
            assert row["pipeline_run_id"] == "canonical-run-002", (
                f"pipeline_run_id must be the canonical run_id, got {row['pipeline_run_id']}"
            )

    def test_counters_default_to_zero(
        self, test_db: Path, skip_live: None
    ) -> None:
        """C3 inserts with all counters at 0 — C4/C5 update them later."""
        ingester = GmailIngester(credentials=None, db_path=test_db)
        ingester.fetch_for_sender(
            "linkedin",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            run_id="sub-run-003",
            canonical_run_id="canonical-run-003",
        )
        rows = _get_log_rows(test_db)
        for row in rows:
            assert row["urls_extracted_count"] == 0
            assert row["urls_new_count"] == 0
            assert row["postings_created_count"] == 0
            assert row["postings_hydrated_count"] == 0
            assert row["postings_hydration_failed_count"] == 0

    def test_idempotent_refetch_does_not_duplicate(
        self, test_db: Path, skip_live: None
    ) -> None:
        """Re-fetching the same emails (same message IDs) must not create duplicate rows."""
        ingester = GmailIngester(credentials=None, db_path=test_db)
        emails = ingester.fetch_for_sender(
            "linkedin",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            run_id="sub-run-004a",
            canonical_run_id="canonical-run-004",
        )
        count_after_first = _count_log_rows(test_db)

        ingester.fetch_for_sender(
            "linkedin",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            run_id="sub-run-004b",
            canonical_run_id="canonical-run-004",
        )
        count_after_second = _count_log_rows(test_db)

        assert count_after_second == count_after_first, (
            "Re-fetching same emails created duplicate email_ingest_log rows"
        )

    def test_canonical_run_id_stored_not_sub_run(
        self, test_db: Path, skip_live: None
    ) -> None:
        """The log row must store the canonical run_id, not the _ingest_<sender> sub-run-id."""
        canonical = "orch-run-xyz"
        sub = f"{canonical}_ingest_linkedin"
        ingester = GmailIngester(credentials=None, db_path=test_db)
        ingester.fetch_for_sender(
            "linkedin",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            run_id=sub,
            canonical_run_id=canonical,
        )
        rows = _get_log_rows(test_db)
        for row in rows:
            assert row["pipeline_run_id"] == canonical, (
                f"Expected pipeline_run_id={canonical!r}, got {row['pipeline_run_id']!r}. "
                "C3 must write the canonical orchestrator run_id, not the sub-run-id."
            )
