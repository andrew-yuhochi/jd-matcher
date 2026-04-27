"""Tests for TASK-M2-001: M2 schema additions (4 new tables + email_ingest_log delta)."""

from __future__ import annotations

import sqlite3

import pytest

from jd_matcher.db.init_db import init_db

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

NEW_M2_TABLES = {
    "canonical_postings",
    "posting_canonical_links",
    "posting_embeddings",
    "llm_call_ledger",
}

NEW_M2_INDEXES = {
    "idx_canonical_user_block",
    "idx_canonical_user_first_seen",
    "idx_links_canonical",
    "idx_links_posting",
    "idx_links_repost",
    "idx_embeddings_user_model",
    "idx_ledger_user_called",
    "idx_ledger_user_kind",
}


@pytest.fixture()
def tmp_db(tmp_path):
    """Return a Path to a freshly initialised test database."""
    db_path = tmp_path / "test_m2.db"
    init_db(db_path)
    return db_path


# ---------------------------------------------------------------------------
# Table existence
# ---------------------------------------------------------------------------


def test_all_4_new_tables_exist(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()
        table_names = {r[0] for r in rows if not r[0].startswith("sqlite_")}
    finally:
        conn.close()
    for table in NEW_M2_TABLES:
        assert table in table_names, f"Expected M2 table '{table}' not found"


# ---------------------------------------------------------------------------
# Index existence
# ---------------------------------------------------------------------------


def test_all_8_new_indexes_exist(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name;"
        ).fetchall()
        index_names = {r[0] for r in rows}
    finally:
        conn.close()
    for idx in NEW_M2_INDEXES:
        assert idx in index_names, f"Expected M2 index '{idx}' not found"


# ---------------------------------------------------------------------------
# posting_canonical_links UNIQUE constraint
# ---------------------------------------------------------------------------


def test_posting_canonical_links_unique_user_posting(tmp_db):
    """UNIQUE(user_id, posting_id) — a posting links to exactly one canonical."""
    now = "2026-04-27T00:00:00Z"
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")  # skip FK checks for this isolation test
    try:
        # Insert a canonical
        conn.execute(
            "INSERT INTO canonical_postings "
            "(canonical_title, canonical_company, canonical_seniority, canonical_location, "
            "top_skills, role_summary, full_jd, full_jd_provenance, "
            "first_seen, last_seen, sources_summary) "
            "VALUES ('Data Scientist', 'Acme', 'mid', 'Vancouver', '[]', 'summary', "
            "'full jd', '{}', ?, ?, '[\"linkedin\"]');",
            (now, now),
        )
        conn.commit()

        # First link — must succeed
        conn.execute(
            "INSERT INTO posting_canonical_links "
            "(user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at) "
            "VALUES ('default', 'posting-1', 1, 1.0, 'new_canonical', ?);",
            (now,),
        )
        conn.commit()

        # Second link for the same (user_id, posting_id) — must fail
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO posting_canonical_links "
                "(user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at) "
                "VALUES ('default', 'posting-1', 1, 0.95, 'content_dedup', ?);",
                (now,),
            )
            conn.commit()
        conn.rollback()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# email_ingest_log filter columns
# ---------------------------------------------------------------------------


def test_email_ingest_log_has_filter_columns(tmp_db):
    """filter_status and filter_reason must exist after init."""
    conn = sqlite3.connect(tmp_db)
    try:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(email_ingest_log);").fetchall()
        }
    finally:
        conn.close()
    assert "filter_status" in columns, "email_ingest_log missing filter_status"
    assert "filter_reason" in columns, "email_ingest_log missing filter_reason"


def test_filter_columns_nullable(tmp_db):
    """filter_status and filter_reason default to NULL (not required at insert)."""
    now = "2026-04-27T00:00:00Z"
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            "INSERT INTO email_ingest_log "
            "(user_id, gmail_message_id, source, sender, subject, "
            "received_at, ingested_at, pipeline_run_id) "
            "VALUES ('default', 'msg-001', 'gmail_linkedin', 'noreply@linkedin.com', "
            "'Job Alert', ?, ?, 'run-001');",
            (now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT filter_status, filter_reason FROM email_ingest_log "
            "WHERE gmail_message_id = 'msg-001';"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] is None, "filter_status should default to NULL"
    assert row[1] is None, "filter_reason should default to NULL"


# ---------------------------------------------------------------------------
# Idempotency on a populated database
# ---------------------------------------------------------------------------


def test_idempotency_on_populated_db(tmp_path):
    """Re-running init_db on a populated DB preserves all rows and columns."""
    now = "2026-04-27T00:00:00Z"
    db_path = tmp_path / "populated.db"

    # ── First init ──────────────────────────────────────────────────────────
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        # Seed rows into several tables
        conn.execute(
            "INSERT INTO postings (canonical_company, canonical_title, hydration_status, first_seen, last_seen) "
            "VALUES ('Acme', 'Data Scientist', 'complete', ?, ?);",
            (now, now),
        )
        conn.execute(
            "INSERT INTO email_ingest_log "
            "(user_id, gmail_message_id, source, sender, subject, "
            "received_at, ingested_at, pipeline_run_id, filter_status) "
            "VALUES ('default', 'msg-idempotent', 'gmail_linkedin', 'n@l.com', "
            "'Alert', ?, ?, 'run-1', 'filtered');",
            (now, now),
        )
        conn.execute(
            "INSERT INTO canonical_postings "
            "(canonical_title, canonical_company, canonical_seniority, canonical_location, "
            "top_skills, role_summary, full_jd, full_jd_provenance, "
            "first_seen, last_seen, sources_summary) "
            "VALUES ('DS', 'Corp', 'mid', 'Remote', '[]', 'summary', 'jd', '{}', ?, ?, '[\"indeed\"]');",
            (now, now),
        )
        conn.commit()

        before_postings = conn.execute("SELECT count(*) FROM postings;").fetchone()[0]
        before_email = conn.execute("SELECT count(*) FROM email_ingest_log;").fetchone()[0]
        before_canonical = conn.execute("SELECT count(*) FROM canonical_postings;").fetchone()[0]
        before_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(email_ingest_log);").fetchall()
        }
    finally:
        conn.close()

    # ── Second init (on populated DB) ────────────────────────────────────────
    init_db(db_path)  # must not raise, must not drop rows

    conn = sqlite3.connect(db_path)
    try:
        after_postings = conn.execute("SELECT count(*) FROM postings;").fetchone()[0]
        after_email = conn.execute("SELECT count(*) FROM email_ingest_log;").fetchone()[0]
        after_canonical = conn.execute("SELECT count(*) FROM canonical_postings;").fetchone()[0]
        after_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(email_ingest_log);").fetchall()
        }
    finally:
        conn.close()

    assert after_postings == before_postings, "postings rows dropped after re-init"
    assert after_email == before_email, "email_ingest_log rows dropped after re-init"
    assert after_canonical == before_canonical, "canonical_postings rows dropped after re-init"
    assert after_columns == before_columns, "email_ingest_log column set changed after re-init"
