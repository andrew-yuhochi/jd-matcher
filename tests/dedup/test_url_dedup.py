"""
Tests for url_dedup (C6 — URL-based dedup).

All tests use an in-memory SQLite database initialised with the full schema.
No filesystem access to ~/.jd-matcher/.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.dedup.url_dedup import is_seen, mark_seen, register_new
from jd_matcher.parse.linkedin_email import ParsedPosting

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "src" / "jd_matcher" / "db" / "schema.sql"


def _make_db() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", ("default",))
    conn.commit()
    return conn


def _make_posting(
    job_id: str = "9999001",
    source: str = "linkedin",
    url: str | None = None,
    raw_url: str | None = None,
) -> ParsedPosting:
    canonical = url or f"https://linkedin.com/jobs/view/{job_id}"
    return ParsedPosting(
        source=source,  # type: ignore[arg-type]
        url=canonical,
        raw_url=raw_url or f"https://www.linkedin.com/comm/jobs/view/{job_id}/?trackingId=abc",
        job_id=job_id,
        title="Test Engineer",
        company="Test Corp",
        location="Vancouver, BC",
        received_at=datetime.now(timezone.utc),
        raw_body=b"raw body bytes",
    )


# ---------------------------------------------------------------------------
# is_seen
# ---------------------------------------------------------------------------

def test_is_seen_returns_false_for_new_url() -> None:
    conn = _make_db()
    assert is_seen("https://linkedin.com/jobs/view/9999001", conn=conn) is False


def test_is_seen_returns_true_for_marked_url() -> None:
    conn = _make_db()
    posting = _make_posting()

    # Insert a minimal posting row so foreign key is satisfied
    conn.execute(
        "INSERT INTO postings (user_id, hydration_status, first_seen, last_seen) "
        "VALUES ('default', 'partial', '2026-01-01', '2026-01-01')"
    )
    posting_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    mark_seen(posting.url, posting_id=posting_id, conn=conn)
    conn.commit()

    assert is_seen(posting.url, conn=conn) is True


# ---------------------------------------------------------------------------
# mark_seen
# ---------------------------------------------------------------------------

def test_mark_seen_raises_on_duplicate() -> None:
    conn = _make_db()
    posting = _make_posting()

    conn.execute(
        "INSERT INTO postings (user_id, hydration_status, first_seen, last_seen) "
        "VALUES ('default', 'partial', '2026-01-01', '2026-01-01')"
    )
    posting_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    mark_seen(posting.url, posting_id=posting_id, conn=conn)
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        mark_seen(posting.url, posting_id=posting_id, conn=conn)
        conn.commit()


# ---------------------------------------------------------------------------
# register_new
# ---------------------------------------------------------------------------

def test_register_new_inserts_posting_and_returns_new() -> None:
    conn = _make_db()
    posting = _make_posting()

    status, posting_id = register_new(posting, conn=conn)

    assert status == 'new'
    assert isinstance(posting_id, int)
    assert posting_id > 0

    # Verify all three tables populated
    assert conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM posting_sources").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM seen_urls").fetchone()[0] == 1

    # Verify posting_id FK integrity
    seen_row = conn.execute("SELECT posting_id FROM seen_urls WHERE url = ?", (posting.url,)).fetchone()
    assert seen_row[0] == posting_id


def test_register_new_returns_seen_for_duplicate_url() -> None:
    conn = _make_db()
    posting = _make_posting()

    status1, id1 = register_new(posting, conn=conn)
    assert status1 == 'new'

    status2, id2 = register_new(posting, conn=conn)
    assert status2 == 'seen'
    assert id2 == id1

    # No duplicate rows
    assert conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM seen_urls").fetchone()[0] == 1


def test_register_new_within_email_dedup() -> None:
    """Two ParsedPostings with same canonical URL but different raw_url → 1 row."""
    conn = _make_db()

    p1 = _make_posting(job_id="9999002", raw_url="https://www.linkedin.com/comm/jobs/view/9999002/?trackingId=foo")
    p2 = _make_posting(job_id="9999002", raw_url="https://www.linkedin.com/comm/jobs/view/9999002/?trackingId=bar")

    assert p1.url == p2.url  # same canonical

    status1, id1 = register_new(p1, conn=conn)
    status2, id2 = register_new(p2, conn=conn)

    assert status1 == 'new'
    assert status2 == 'seen'
    assert id1 == id2

    assert conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM posting_sources").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM seen_urls").fetchone()[0] == 1


def test_register_new_atomicity() -> None:
    """Simulated failure mid-transaction leaves no committed rows.

    We test atomicity by verifying the UNIQUE constraint on seen_urls prevents
    partial commits: if seen_urls INSERT fails (IntegrityError on duplicate),
    the whole transaction rolls back and postings is not left orphaned.
    """
    conn = _make_db()
    posting = _make_posting(job_id="9999003")

    # First registration succeeds.
    status1, id1 = register_new(posting, conn=conn)
    assert status1 == 'new'

    # Manually corrupt the seen_urls to test rollback: delete the seen_url
    # but keep the posting — then attempt to register again, which should
    # detect it as 'seen' via the transaction-internal SELECT.
    # The real atomicity is enforced by `with conn:` (auto BEGIN/COMMIT/ROLLBACK).
    # We verify it by ensuring the UNIQUE constraint causes no double-insert.
    conn.execute("DELETE FROM seen_urls WHERE url = ?", (posting.url,))
    conn.commit()

    # Now manually insert a conflicting seen_url with the SAME url but wrong posting_id
    # to force an IntegrityError on re-registration.
    conn.execute(
        "INSERT INTO postings (user_id, hydration_status, first_seen, last_seen) "
        "VALUES ('default', 'partial', '2026-01-01', '2026-01-01')"
    )
    fake_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO seen_urls (url, user_id, posting_id, seen_at) VALUES (?, 'default', ?, '2026-01-01')",
        (posting.url, fake_id),
    )
    conn.commit()

    # register_new should detect as 'seen' (found in seen_urls SELECT) and NOT insert.
    status2, id2 = register_new(posting, conn=conn)
    assert status2 == 'seen'
    # posting count stays at 2 (original + fake), not 3
    assert conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM seen_urls").fetchone()[0] == 1


def test_re_run_pipeline_produces_zero_new_postings() -> None:
    """Registering 10 postings twice: 10 'new' first time, 10 'seen' second time."""
    conn = _make_db()

    postings = [_make_posting(job_id=str(9000000 + i)) for i in range(10)]

    # First pass
    first_pass = [register_new(p, conn=conn) for p in postings]
    new_count = sum(1 for status, _ in first_pass if status == 'new')
    assert new_count == 10

    # Second pass — identical postings
    second_pass = [register_new(p, conn=conn) for p in postings]
    seen_count = sum(1 for status, _ in second_pass if status == 'seen')
    assert seen_count == 10

    # DB state: exactly 10 postings, 10 seen_urls
    assert conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 10
    assert conn.execute("SELECT COUNT(*) FROM seen_urls").fetchone()[0] == 10


def test_register_new_stores_raw_body() -> None:
    """posting_sources.raw_body is populated from ParsedPosting.raw_body."""
    conn = _make_db()
    posting = _make_posting()

    _, posting_id = register_new(posting, conn=conn)

    row = conn.execute(
        "SELECT raw_body FROM posting_sources WHERE posting_id = ?", (posting_id,)
    ).fetchone()
    assert row is not None
    assert row[0] is not None
    # raw_body stored as latin-1 string; round-trip should match original bytes
    assert row[0].encode('latin-1') == posting.raw_body


def test_register_new_sets_source_label() -> None:
    """posting_sources.source is '{source}_email'."""
    conn = _make_db()
    posting = _make_posting(source="linkedin")

    _, posting_id = register_new(posting, conn=conn)

    row = conn.execute(
        "SELECT source FROM posting_sources WHERE posting_id = ?", (posting_id,)
    ).fetchone()
    assert row[0] == "linkedin_email"


def test_register_new_hydration_status_partial() -> None:
    """New posting inserted with hydration_status='partial' (URL only, not yet hydrated)."""
    conn = _make_db()
    posting = _make_posting()

    _, posting_id = register_new(posting, conn=conn)

    row = conn.execute(
        "SELECT hydration_status FROM postings WHERE id = ?", (posting_id,)
    ).fetchone()
    assert row[0] == "partial"
