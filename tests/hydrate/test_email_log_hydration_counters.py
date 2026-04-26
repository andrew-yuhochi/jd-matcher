"""
Tests for the C5 email_ingest_log hydration counter update (AC #4).

Verifies:
  - increment_hydration increments postings_hydrated_count on success
  - increment_hydration increments postings_hydration_failed_count on failure
  - Multiple postings from the same email accumulate correctly
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.db.email_ingest_log import insert_email_log, increment_hydration


@pytest.fixture()
def test_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


def _insert_stub_row(db_path: Path, gmail_message_id: str) -> None:
    now = datetime.now(timezone.utc)
    insert_email_log(
        gmail_message_id=gmail_message_id,
        source="linkedin",
        sender="jobalerts@linkedin.com",
        subject="Test subject",
        received_at=now,
        pipeline_run_id="run-hydrate-001",
        db_path=db_path,
    )


def _get_hydration_counts(db_path: Path, gmail_message_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT postings_hydrated_count, postings_hydration_failed_count
            FROM email_ingest_log WHERE gmail_message_id = ?
            """,
            (gmail_message_id,),
        ).fetchone()
        return {"hydrated": row[0], "failed": row[1]} if row else {}
    finally:
        conn.close()


class TestC5HydrationCounters:
    def test_increment_hydrated_on_success(self, test_db: Path) -> None:
        _insert_stub_row(test_db, "msg-hydrate-001")
        increment_hydration(gmail_message_id="msg-hydrate-001", success=True, db_path=test_db)
        counts = _get_hydration_counts(test_db, "msg-hydrate-001")
        assert counts["hydrated"] == 1
        assert counts["failed"] == 0

    def test_increment_failed_on_failure(self, test_db: Path) -> None:
        _insert_stub_row(test_db, "msg-hydrate-002")
        increment_hydration(gmail_message_id="msg-hydrate-002", success=False, db_path=test_db)
        counts = _get_hydration_counts(test_db, "msg-hydrate-002")
        assert counts["hydrated"] == 0
        assert counts["failed"] == 1

    def test_multiple_postings_accumulate(self, test_db: Path) -> None:
        """3 successes + 2 failures from the same email must accumulate."""
        _insert_stub_row(test_db, "msg-hydrate-003")
        for _ in range(3):
            increment_hydration(gmail_message_id="msg-hydrate-003", success=True, db_path=test_db)
        for _ in range(2):
            increment_hydration(gmail_message_id="msg-hydrate-003", success=False, db_path=test_db)
        counts = _get_hydration_counts(test_db, "msg-hydrate-003")
        assert counts["hydrated"] == 3
        assert counts["failed"] == 2

    def test_two_emails_tracked_independently(self, test_db: Path) -> None:
        """Hydration outcomes for different emails must not bleed across rows."""
        _insert_stub_row(test_db, "msg-hydrate-004")
        _insert_stub_row(test_db, "msg-hydrate-005")

        increment_hydration(gmail_message_id="msg-hydrate-004", success=True, db_path=test_db)
        increment_hydration(gmail_message_id="msg-hydrate-005", success=False, db_path=test_db)

        counts_004 = _get_hydration_counts(test_db, "msg-hydrate-004")
        counts_005 = _get_hydration_counts(test_db, "msg-hydrate-005")

        assert counts_004 == {"hydrated": 1, "failed": 0}
        assert counts_005 == {"hydrated": 0, "failed": 1}

    def test_increment_on_nonexistent_row_is_silent(self, test_db: Path) -> None:
        """incrementing a non-existent gmail_message_id should not raise."""
        increment_hydration(gmail_message_id="nonexistent", success=True, db_path=test_db)
