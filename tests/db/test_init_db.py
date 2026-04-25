"""Tests for jd_matcher.db.init_db — schema correctness and idempotency."""

from __future__ import annotations

import sqlite3

import pytest

from jd_matcher.db.init_db import init_db

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

ALL_TABLES = {
    "users",
    "postings",
    "posting_sources",
    "seen_urls",
    "applied",
    "dismissed",
    "events",
    "pipeline_runs",
}


@pytest.fixture()
def tmp_db(tmp_path):
    """Return a Path to a freshly initialised test database."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_init_db_creates_database(tmp_path):
    db_path = tmp_path / "test.db"
    assert not db_path.exists()
    init_db(db_path)
    assert db_path.exists()


def test_init_db_creates_all_8_tables(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()
        # sqlite_sequence is an internal SQLite table; exclude it from the check.
        table_names = {r[0] for r in rows if not r[0].startswith("sqlite_")}
    finally:
        conn.close()
    assert table_names == ALL_TABLES


def test_init_db_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    init_db(db_path)  # must not raise

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT count(*) FROM users;").fetchone()[0]
    finally:
        conn.close()
    assert count == 1, "INSERT OR IGNORE must not create duplicate 'default' user"


def test_init_db_user_id_present_on_every_table(tmp_db):
    # The `users` table itself is the identity anchor; it has `id` not `user_id`.
    # Every other table references the user namespace via `user_id`.
    tables_requiring_user_id = ALL_TABLES - {"users"}
    conn = sqlite3.connect(tmp_db)
    try:
        for table in tables_requiring_user_id:
            columns = {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table});").fetchall()
            }
            assert "user_id" in columns, f"Table '{table}' is missing user_id column"
    finally:
        conn.close()


def test_postings_hydration_status_check(tmp_db):
    now = "2026-04-24T00:00:00Z"

    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        # Invalid value must be rejected
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO postings (hydration_status, first_seen, last_seen) "
                "VALUES ('invalid', ?, ?);",
                (now, now),
            )
            conn.commit()
        conn.rollback()

        # All three valid values must be accepted
        for status in ("complete", "partial", "failed"):
            conn.execute(
                "INSERT INTO postings (hydration_status, first_seen, last_seen) "
                "VALUES (?, ?, ?);",
                (status, now, now),
            )
        conn.commit()
    finally:
        conn.close()


def test_pipeline_runs_health_status_check(tmp_db):
    now = "2026-04-24T00:00:00Z"

    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, source, health_status, started_at) "
                "VALUES ('r1', 'gmail_linkedin', 'unknown', ?);",
                (now,),
            )
            conn.commit()
        conn.rollback()

        for status in ("healthy", "degraded", "failed"):
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, source, health_status, started_at) "
                "VALUES (?, 'gmail_linkedin', ?, ?);",
                (f"run-{status}", status, now),
            )
        conn.commit()
    finally:
        conn.close()


def test_seen_urls_unique_constraint(tmp_db):
    now = "2026-04-24T00:00:00Z"

    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        # Insert a posting to satisfy the FK on seen_urls.posting_id
        conn.execute(
            "INSERT INTO postings (id, hydration_status, first_seen, last_seen) "
            "VALUES (1, 'complete', ?, ?);",
            (now, now),
        )
        conn.commit()

        conn.execute(
            "INSERT INTO seen_urls (url, user_id, posting_id, seen_at) "
            "VALUES ('https://example.com/job/1', 'default', 1, ?);",
            (now,),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO seen_urls (url, user_id, posting_id, seen_at) "
                "VALUES ('https://example.com/job/1', 'default', 1, ?);",
                (now,),
            )
            conn.commit()
    finally:
        conn.close()


def test_applied_dismissed_unique_per_posting(tmp_db):
    now = "2026-04-24T00:00:00Z"

    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.execute(
            "INSERT INTO postings (id, hydration_status, first_seen, last_seen) "
            "VALUES (10, 'complete', ?, ?);",
            (now, now),
        )
        conn.commit()

        # applied UNIQUE(user_id, posting_id)
        conn.execute(
            "INSERT INTO applied (posting_id, user_id, applied_at, status_updated_at) "
            "VALUES (10, 'default', ?, ?);",
            (now, now),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO applied (posting_id, user_id, applied_at, status_updated_at) "
                "VALUES (10, 'default', ?, ?);",
                (now, now),
            )
            conn.commit()
        conn.rollback()

        # dismissed UNIQUE(user_id, posting_id)
        conn.execute(
            "INSERT INTO dismissed (posting_id, user_id, dismissed_at) "
            "VALUES (10, 'default', ?);",
            (now,),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO dismissed (posting_id, user_id, dismissed_at) "
                "VALUES (10, 'default', ?);",
                (now,),
            )
            conn.commit()
        conn.rollback()
    finally:
        conn.close()


def test_smoke_insert_and_query(tmp_db):
    """Happy-path roundtrip: posting → posting_source → seen_url → applied."""
    now = "2026-04-24T00:00:00Z"
    url = "https://linkedin.com/jobs/view/12345"

    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        # Insert posting
        cur = conn.execute(
            "INSERT INTO postings "
            "(canonical_company, canonical_title, hydration_status, first_seen, last_seen) "
            "VALUES ('Acme Corp', 'Data Scientist', 'complete', ?, ?);",
            (now, now),
        )
        posting_id = cur.lastrowid
        conn.commit()

        # Insert posting source
        conn.execute(
            "INSERT INTO posting_sources "
            "(posting_id, source, source_url, source_first_seen) "
            "VALUES (?, 'linkedin_email', ?, ?);",
            (posting_id, url, now),
        )
        conn.commit()

        # Insert seen_url
        conn.execute(
            "INSERT INTO seen_urls (url, user_id, posting_id, seen_at) "
            "VALUES (?, 'default', ?, ?);",
            (url, posting_id, now),
        )
        conn.commit()

        # Apply transition
        conn.execute(
            "INSERT INTO applied (posting_id, user_id, applied_at, status_updated_at) "
            "VALUES (?, 'default', ?, ?);",
            (posting_id, now, now),
        )
        conn.commit()

        # Verify roundtrip
        row = conn.execute(
            "SELECT canonical_company, canonical_title FROM postings WHERE id = ?;",
            (posting_id,),
        ).fetchone()
        assert row == ("Acme Corp", "Data Scientist")

        applied_row = conn.execute(
            "SELECT status FROM applied WHERE posting_id = ?;",
            (posting_id,),
        ).fetchone()
        assert applied_row[0] == "Applied"

        seen_row = conn.execute(
            "SELECT posting_id FROM seen_urls WHERE url = ?;",
            (url,),
        ).fetchone()
        assert seen_row[0] == posting_id
    finally:
        conn.close()
