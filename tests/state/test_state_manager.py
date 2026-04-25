"""
Integration tests for jd_matcher.state.manager (C7 — State Manager).

Coverage:
  - mark_applied: creates applied row with status='Applied'
  - dismiss: creates dismissed row; idempotent on re-dismiss
  - restore: deletes dismissed row; no-op if not dismissed
  - main_view_postings: excludes applied and dismissed postings
  - server-restart persistence: state survives closing and reopening connection
  - auto_remove_stale_applied: removes stale rows, preserves status='Offer'
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.state.manager import (
    StateTransition,
    auto_remove_stale_applied,
    dismiss,
    main_view_postings,
    mark_applied,
    restore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path):
    """Initialised test database; returns the Path."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


def _insert_posting(conn: sqlite3.Connection, title: str, ts: str) -> int:
    """Insert a minimal posting and return its id."""
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


# ---------------------------------------------------------------------------
# mark_applied
# ---------------------------------------------------------------------------


def test_mark_applied_creates_row_with_applied_status(db):
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Data Scientist", "2026-04-25T00:00:00Z")

    transition = mark_applied(pid, conn=conn)

    assert isinstance(transition, StateTransition)
    assert transition.posting_id == pid
    assert transition.to_state == "Applied"

    row = conn.execute(
        "SELECT status FROM applied WHERE posting_id = ? AND user_id = 'default'",
        (pid,),
    ).fetchone()
    assert row is not None
    assert row[0] == "Applied"
    conn.close()


def test_mark_applied_sets_applied_at_and_status_updated_at(db):
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "ML Engineer", "2026-04-25T00:00:00Z")

    mark_applied(pid, conn=conn)

    row = conn.execute(
        "SELECT applied_at, status_updated_at FROM applied WHERE posting_id = ?",
        (pid,),
    ).fetchone()
    assert row[0] is not None
    assert row[1] is not None
    conn.close()


def test_mark_applied_idempotent(db):
    """Re-applying is a no-op — UNIQUE constraint; no IntegrityError raised."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Software Engineer", "2026-04-25T00:00:00Z")

    mark_applied(pid, conn=conn)
    mark_applied(pid, conn=conn)  # must not raise

    count = conn.execute(
        "SELECT count(*) FROM applied WHERE posting_id = ?", (pid,)
    ).fetchone()[0]
    assert count == 1
    conn.close()


# ---------------------------------------------------------------------------
# dismiss
# ---------------------------------------------------------------------------


def test_dismiss_creates_dismissed_row(db):
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Product Manager", "2026-04-25T00:00:00Z")

    transition = dismiss(pid, conn=conn)

    assert isinstance(transition, StateTransition)
    assert transition.posting_id == pid
    assert transition.to_state == "dismissed"

    row = conn.execute(
        "SELECT dismissed_at FROM dismissed WHERE posting_id = ?", (pid,)
    ).fetchone()
    assert row is not None
    conn.close()


def test_dismiss_idempotent(db):
    """Re-dismissing is a no-op — no IntegrityError raised."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "UX Designer", "2026-04-25T00:00:00Z")

    dismiss(pid, conn=conn)
    dismiss(pid, conn=conn)  # must not raise

    count = conn.execute(
        "SELECT count(*) FROM dismissed WHERE posting_id = ?", (pid,)
    ).fetchone()[0]
    assert count == 1
    conn.close()


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


def test_restore_deletes_dismissed_row(db):
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "DevOps Engineer", "2026-04-25T00:00:00Z")

    dismiss(pid, conn=conn)
    row_before = conn.execute(
        "SELECT 1 FROM dismissed WHERE posting_id = ?", (pid,)
    ).fetchone()
    assert row_before is not None

    transition = restore(pid, conn=conn)

    assert isinstance(transition, StateTransition)
    assert transition.posting_id == pid
    assert transition.from_state == "dismissed"

    row_after = conn.execute(
        "SELECT 1 FROM dismissed WHERE posting_id = ?", (pid,)
    ).fetchone()
    assert row_after is None
    conn.close()


def test_restore_noop_when_not_dismissed(db):
    """Restoring a posting that was never dismissed must not raise."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Backend Engineer", "2026-04-25T00:00:00Z")

    restore(pid, conn=conn)  # must not raise

    count = conn.execute(
        "SELECT count(*) FROM dismissed WHERE posting_id = ?", (pid,)
    ).fetchone()[0]
    assert count == 0
    conn.close()


# ---------------------------------------------------------------------------
# main_view_postings
# ---------------------------------------------------------------------------


def test_main_view_excludes_applied_and_dismissed(db):
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")

    ts = "2026-04-25T00:00:00Z"
    pid_main = _insert_posting(conn, "Visible", ts)
    pid_applied = _insert_posting(conn, "Applied Away", ts)
    pid_dismissed = _insert_posting(conn, "Dismissed Away", ts)

    mark_applied(pid_applied, conn=conn)
    dismiss(pid_dismissed, conn=conn)

    postings = main_view_postings(conn=conn)
    ids = {p.id for p in postings}

    assert pid_main in ids
    assert pid_applied not in ids
    assert pid_dismissed not in ids
    conn.close()


def test_main_view_returns_posting_objects(db):
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid = _insert_posting(conn, "Data Engineer", "2026-04-25T00:00:00Z")

    postings = main_view_postings(conn=conn)

    assert len(postings) == 1
    p = postings[0]
    assert p.id == pid
    assert p.canonical_title == "Data Engineer"
    assert p.user_id == "default"
    conn.close()


def test_main_view_ordered_by_first_seen_desc(db):
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")

    pid_old = _insert_posting(conn, "Old Job", "2026-04-20T00:00:00Z")
    pid_new = _insert_posting(conn, "New Job", "2026-04-25T00:00:00Z")

    postings = main_view_postings(conn=conn)
    ids = [p.id for p in postings]

    assert ids.index(pid_new) < ids.index(pid_old)
    conn.close()


# ---------------------------------------------------------------------------
# Server-restart persistence (integration)
# ---------------------------------------------------------------------------


def test_state_persists_across_connection_restart(db):
    """Close connection, reopen it, confirm state is still there."""
    # Write state
    conn1 = sqlite3.connect(str(db))
    conn1.execute("PRAGMA foreign_keys = ON;")
    ts = "2026-04-25T00:00:00Z"
    pid_applied = _insert_posting(conn1, "Applied Job", ts)
    pid_dismissed = _insert_posting(conn1, "Dismissed Job", ts)
    pid_main = _insert_posting(conn1, "Main Job", ts)
    mark_applied(pid_applied, conn=conn1)
    dismiss(pid_dismissed, conn=conn1)
    conn1.commit()  # caller owns the commit when passing explicit conn
    conn1.close()  # simulate server restart

    # Reopen and verify
    conn2 = sqlite3.connect(str(db))
    conn2.execute("PRAGMA foreign_keys = ON;")

    applied_row = conn2.execute(
        "SELECT status FROM applied WHERE posting_id = ?", (pid_applied,)
    ).fetchone()
    assert applied_row is not None
    assert applied_row[0] == "Applied"

    dismissed_row = conn2.execute(
        "SELECT 1 FROM dismissed WHERE posting_id = ?", (pid_dismissed,)
    ).fetchone()
    assert dismissed_row is not None

    postings = main_view_postings(conn=conn2)
    ids = {p.id for p in postings}
    assert pid_main in ids
    assert pid_applied not in ids
    assert pid_dismissed not in ids

    conn2.close()


# ---------------------------------------------------------------------------
# auto_remove_stale_applied
# ---------------------------------------------------------------------------


def test_auto_remove_stale_applied_removes_old_rows(db):
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")

    ts_old = "2026-01-01T00:00:00Z"
    ts_new = "2026-04-25T00:00:00Z"
    pid_old = _insert_posting(conn, "Old Applied", ts_old)
    pid_new = _insert_posting(conn, "New Applied", ts_new)

    # Insert applied rows with different applied_at
    conn.execute(
        "INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at) "
        "VALUES (?, 'default', 'Applied', ?, ?)",
        (pid_old, ts_old, ts_old),
    )
    conn.execute(
        "INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at) "
        "VALUES (?, 'default', 'Applied', ?, ?)",
        (pid_new, ts_new, ts_new),
    )
    conn.commit()

    cutoff = date(2026, 4, 1)
    removed = auto_remove_stale_applied(cutoff, conn=conn)

    assert removed == 1

    remaining = conn.execute(
        "SELECT posting_id FROM applied WHERE user_id = 'default'"
    ).fetchall()
    remaining_ids = {r[0] for r in remaining}
    assert pid_old not in remaining_ids
    assert pid_new in remaining_ids
    conn.close()


def test_auto_remove_stale_applied_preserves_offer_status(db):
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")

    ts_old = "2026-01-01T00:00:00Z"
    pid = _insert_posting(conn, "Offer Job", ts_old)

    conn.execute(
        "INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at) "
        "VALUES (?, 'default', 'Offer', ?, ?)",
        (pid, ts_old, ts_old),
    )
    conn.commit()

    cutoff = date(2026, 4, 1)
    removed = auto_remove_stale_applied(cutoff, conn=conn)

    assert removed == 0

    row = conn.execute(
        "SELECT status FROM applied WHERE posting_id = ?", (pid,)
    ).fetchone()
    assert row is not None
    assert row[0] == "Offer"
    conn.close()


def test_auto_remove_stale_applied_returns_count(db):
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")

    ts_old = "2026-01-01T00:00:00Z"
    for i in range(3):
        pid = _insert_posting(conn, f"Old Job {i}", ts_old)
        conn.execute(
            "INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at) "
            "VALUES (?, 'default', 'Applied', ?, ?)",
            (pid, ts_old, ts_old),
        )
    conn.commit()

    removed = auto_remove_stale_applied(date(2026, 4, 1), conn=conn)
    assert removed == 3
    conn.close()


def test_auto_remove_stale_applied_noop_when_nothing_stale(db):
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")

    removed = auto_remove_stale_applied(date(2026, 1, 1), conn=conn)
    assert removed == 0
    conn.close()
