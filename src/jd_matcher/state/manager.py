"""
State manager (C7) — applied / dismissed / restore transitions.

Public API (names canonical per TASKS.md ACs):
  mark_applied(posting_id, ...)  -> StateTransition
  dismiss(posting_id, ...)       -> StateTransition
  restore(posting_id, ...)       -> StateTransition
  main_view_postings(...)        -> list[Posting]
  auto_remove_stale_applied(cutoff_date, ...) -> int

All functions accept optional user_id (default 'default') and optional
sqlite3.Connection.  When conn=None they open and close their own connection,
matching the pattern in jd_matcher.dedup.url_dedup.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class StateTransition:
    """Record of a single state transition for a posting."""

    posting_id: int
    from_state: str
    to_state: str
    ts: datetime


@dataclass
class Posting:
    """Minimal projection of the postings table for main-view display."""

    id: int
    user_id: str
    canonical_company: Optional[str]
    canonical_title: Optional[str]
    canonical_location: Optional[str]
    hydration_status: str
    first_seen: str
    last_seen: str


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


def _open_conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or _DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


def mark_applied(
    posting_id: int,
    user_id: str = "default",
    conn: Optional[sqlite3.Connection] = None,
    db_path: Path | None = None,
) -> StateTransition:
    """Insert into applied; idempotent via UNIQUE(user_id, posting_id) constraint.

    If a row already exists for this (user_id, posting_id), the existing row
    is left unchanged (INSERT OR IGNORE semantics).
    """
    own_conn = conn is None
    c = conn if conn is not None else _open_conn(db_path)
    now = _now_iso()
    try:
        c.execute(
            """
            INSERT OR IGNORE INTO applied
                (posting_id, user_id, status, applied_at, status_updated_at)
            VALUES (?, ?, 'Applied', ?, ?)
            """,
            (posting_id, user_id, now, now),
        )
        if own_conn:
            c.commit()
        logger.debug("mark_applied: posting_id=%d user_id=%s", posting_id, user_id)
    finally:
        if own_conn:
            c.close()

    return StateTransition(
        posting_id=posting_id,
        from_state="main",
        to_state="Applied",
        ts=datetime.fromisoformat(now),
    )


def dismiss(
    posting_id: int,
    user_id: str = "default",
    conn: Optional[sqlite3.Connection] = None,
    db_path: Path | None = None,
) -> StateTransition:
    """Insert into dismissed; idempotent — re-dismiss is a no-op."""
    own_conn = conn is None
    c = conn if conn is not None else _open_conn(db_path)
    now = _now_iso()
    try:
        c.execute(
            """
            INSERT OR IGNORE INTO dismissed (posting_id, user_id, dismissed_at)
            VALUES (?, ?, ?)
            """,
            (posting_id, user_id, now),
        )
        if own_conn:
            c.commit()
        logger.debug("dismiss: posting_id=%d user_id=%s", posting_id, user_id)
    finally:
        if own_conn:
            c.close()

    return StateTransition(
        posting_id=posting_id,
        from_state="main",
        to_state="dismissed",
        ts=datetime.fromisoformat(now),
    )


def restore(
    posting_id: int,
    user_id: str = "default",
    conn: Optional[sqlite3.Connection] = None,
    db_path: Path | None = None,
) -> StateTransition:
    """Delete from dismissed, returning the posting to main view.

    If posting_id is not in dismissed, this is a no-op (no error raised).
    """
    own_conn = conn is None
    c = conn if conn is not None else _open_conn(db_path)
    now = _now_iso()
    try:
        c.execute(
            "DELETE FROM dismissed WHERE user_id = ? AND posting_id = ?",
            (user_id, posting_id),
        )
        if own_conn:
            c.commit()
        logger.debug("restore: posting_id=%d user_id=%s", posting_id, user_id)
    finally:
        if own_conn:
            c.close()

    return StateTransition(
        posting_id=posting_id,
        from_state="dismissed",
        to_state="main",
        ts=datetime.fromisoformat(now),
    )


# ---------------------------------------------------------------------------
# Main-view query
# ---------------------------------------------------------------------------


def main_view_postings(
    user_id: str = "default",
    conn: Optional[sqlite3.Connection] = None,
    db_path: Path | None = None,
) -> list[Posting]:
    """Return postings not in applied or dismissed, ordered by first_seen DESC."""
    own_conn = conn is None
    c = conn if conn is not None else _open_conn(db_path)
    try:
        rows = c.execute(
            """
            SELECT id, user_id, canonical_company, canonical_title,
                   canonical_location, hydration_status, first_seen, last_seen
            FROM postings
            WHERE user_id = ?
              AND id NOT IN (SELECT posting_id FROM applied   WHERE user_id = ?)
              AND id NOT IN (SELECT posting_id FROM dismissed WHERE user_id = ?)
            ORDER BY first_seen DESC
            """,
            (user_id, user_id, user_id),
        ).fetchall()
    finally:
        if own_conn:
            c.close()

    return [
        Posting(
            id=row[0],
            user_id=row[1],
            canonical_company=row[2],
            canonical_title=row[3],
            canonical_location=row[4],
            hydration_status=row[5],
            first_seen=row[6],
            last_seen=row[7],
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Auto-removal helper (scheduler deferred to MVP)
# ---------------------------------------------------------------------------


def auto_remove_stale_applied(
    cutoff_date: date,
    user_id: str = "default",
    conn: Optional[sqlite3.Connection] = None,
    db_path: Path | None = None,
) -> int:
    """Remove applied rows where applied_at < cutoff_date and status != 'Offer'.

    Returns the number of rows deleted.
    The scheduler that calls this is deferred to MVP-M1; this helper exists
    in M1 so the logic is unit-testable independently of scheduling machinery.
    """
    own_conn = conn is None
    c = conn if conn is not None else _open_conn(db_path)
    cutoff_iso = cutoff_date.isoformat()
    try:
        cur = c.execute(
            """
            DELETE FROM applied
            WHERE user_id = ?
              AND applied_at < ?
              AND status NOT IN ('Offer')
            """,
            (user_id, cutoff_iso),
        )
        removed = cur.rowcount
        if own_conn:
            c.commit()
        logger.debug(
            "auto_remove_stale_applied: removed=%d cutoff=%s user_id=%s",
            removed,
            cutoff_iso,
            user_id,
        )
        return removed
    finally:
        if own_conn:
            c.close()
