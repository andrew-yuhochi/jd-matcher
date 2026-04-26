"""
Tests for email_ingest_log schema and init_db idempotency (AC #1).

Verifies:
  - email_ingest_log table is created by init_db()
  - Re-running init_db() on an existing populated DB does NOT recreate or fail
  - Required columns exist with correct defaults
  - UNIQUE constraint on gmail_message_id is enforced
  - Indexes are created
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from jd_matcher.db.init_db import init_db


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


def test_email_ingest_log_table_exists(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='email_ingest_log'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "email_ingest_log table not created by init_db()"


def test_init_db_idempotent_with_ingest_log_data(tmp_path):
    """Re-running init_db on a populated DB must not erase rows or raise."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO email_ingest_log
                (gmail_message_id, source, sender, subject, received_at, ingested_at, pipeline_run_id)
            VALUES ('msg-001', 'linkedin', 'test@test.com', 'Test Subject', ?, ?, 'run-001')
            """,
            (now, now),
        )
        conn.commit()
    finally:
        conn.close()

    # Re-run init_db — must not raise, must not delete the row.
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM email_ingest_log").fetchone()[0]
    finally:
        conn.close()

    assert count == 1, f"init_db() deleted email_ingest_log rows (count={count})"


def test_email_ingest_log_columns_exist(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(email_ingest_log)").fetchall()}
    finally:
        conn.close()

    required = {
        "id", "user_id", "gmail_message_id", "source", "sender", "subject",
        "received_at", "ingested_at", "pipeline_run_id",
        "urls_extracted_count", "urls_new_count", "postings_created_count",
        "postings_hydrated_count", "postings_hydration_failed_count", "notes",
    }
    missing = required - cols
    assert not missing, f"Missing columns in email_ingest_log: {missing}"


def test_email_ingest_log_counter_defaults_zero(tmp_db):
    """Counter columns default to 0 when not specified."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            """
            INSERT INTO email_ingest_log
                (gmail_message_id, source, sender, subject, received_at, ingested_at, pipeline_run_id)
            VALUES ('msg-defaults', 'linkedin', 's@s.com', 'Subj', ?, ?, 'run-x')
            """,
            (now, now),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT urls_extracted_count, urls_new_count, postings_created_count,
                   postings_hydrated_count, postings_hydration_failed_count
            FROM email_ingest_log WHERE gmail_message_id = 'msg-defaults'
            """
        ).fetchone()
    finally:
        conn.close()
    assert row == (0, 0, 0, 0, 0), f"Counter defaults are not all 0: {row}"


def test_email_ingest_log_unique_gmail_message_id(tmp_db):
    """UNIQUE constraint on gmail_message_id must reject duplicates."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            """
            INSERT INTO email_ingest_log
                (gmail_message_id, source, sender, subject, received_at, ingested_at, pipeline_run_id)
            VALUES ('dup-msg', 'linkedin', 's@s.com', 'Subj', ?, ?, 'run-1')
            """,
            (now, now),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO email_ingest_log
                    (gmail_message_id, source, sender, subject, received_at, ingested_at, pipeline_run_id)
                VALUES ('dup-msg', 'linkedin', 's@s.com', 'Subj2', ?, ?, 'run-2')
                """,
                (now, now),
            )
            conn.commit()
    finally:
        conn.close()


def test_email_ingest_log_indexes_exist(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        indexes = {
            row[1]
            for row in conn.execute(
                "SELECT type, name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert "idx_email_ingest_log_run" in indexes
    assert "idx_email_ingest_log_received" in indexes
