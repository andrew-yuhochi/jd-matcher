"""
Tests for the C4 email_ingest_log URL counter update (AC #3).

Verifies:
  - update_url_counts sets urls_extracted_count and urls_new_count correctly
  - postings_created_count is also set
  - Multiple calls overwrite (not increment) the counts
  - The row must pre-exist (inserted by C3); no implicit insert
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.db.email_ingest_log import insert_email_log, update_url_counts


@pytest.fixture()
def test_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


def _insert_stub_row(db_path: Path, gmail_message_id: str, pipeline_run_id: str = "run-001") -> None:
    now = datetime.now(timezone.utc)
    insert_email_log(
        gmail_message_id=gmail_message_id,
        source="linkedin",
        sender="jobalerts@linkedin.com",
        subject="Test subject",
        received_at=now,
        pipeline_run_id=pipeline_run_id,
        db_path=db_path,
    )


def _get_counts(db_path: Path, gmail_message_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT urls_extracted_count, urls_new_count, postings_created_count
            FROM email_ingest_log WHERE gmail_message_id = ?
            """,
            (gmail_message_id,),
        ).fetchone()
        return {"extracted": row[0], "new": row[1], "created": row[2]} if row else {}
    finally:
        conn.close()


class TestC4UrlCounterUpdate:
    def test_update_url_counts_sets_extracted_and_new(self, test_db: Path) -> None:
        """C4 update must set both urls_extracted_count and urls_new_count."""
        _insert_stub_row(test_db, "msg-url-001")
        update_url_counts(
            gmail_message_id="msg-url-001",
            urls_extracted_count=10,
            urls_new_count=7,
            postings_created_count=7,
            db_path=test_db,
        )
        counts = _get_counts(test_db, "msg-url-001")
        assert counts["extracted"] == 10
        assert counts["new"] == 7
        assert counts["created"] == 7

    def test_update_url_counts_zero_new_urls(self, test_db: Path) -> None:
        """All URLs seen before — urls_new_count should be 0."""
        _insert_stub_row(test_db, "msg-url-002")
        update_url_counts(
            gmail_message_id="msg-url-002",
            urls_extracted_count=5,
            urls_new_count=0,
            postings_created_count=0,
            db_path=test_db,
        )
        counts = _get_counts(test_db, "msg-url-002")
        assert counts["extracted"] == 5
        assert counts["new"] == 0
        assert counts["created"] == 0

    def test_update_url_counts_overwrites_previous(self, test_db: Path) -> None:
        """A second call to update_url_counts overwrites (not adds to) the counts."""
        _insert_stub_row(test_db, "msg-url-003")
        update_url_counts(
            gmail_message_id="msg-url-003",
            urls_extracted_count=3,
            urls_new_count=2,
            db_path=test_db,
        )
        update_url_counts(
            gmail_message_id="msg-url-003",
            urls_extracted_count=8,
            urls_new_count=5,
            db_path=test_db,
        )
        counts = _get_counts(test_db, "msg-url-003")
        assert counts["extracted"] == 8, "Second update should overwrite, not add"
        assert counts["new"] == 5

    def test_update_url_counts_no_match_is_silent(self, test_db: Path) -> None:
        """Updating a non-existent gmail_message_id should not raise."""
        # Should silently do nothing (0 rows affected)
        update_url_counts(
            gmail_message_id="nonexistent-msg",
            urls_extracted_count=5,
            urls_new_count=3,
            db_path=test_db,
        )
        # Verify table still has 0 rows
        conn = sqlite3.connect(test_db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM email_ingest_log").fetchone()[0]
        finally:
            conn.close()
        assert count == 0
