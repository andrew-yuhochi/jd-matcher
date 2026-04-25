"""
URL-based dedup (C6).

Three public functions:
  is_seen(url, user_id, conn)     — True if (user_id, url) in seen_urls
  mark_seen(url, posting_id, ...)  — INSERT into seen_urls
  register_new(parsed, user_id, conn) — atomic: is_seen → insert postings +
                                        posting_sources + seen_urls if new

All functions accept an optional sqlite3.Connection.  When conn=None they
open and close their own connection to the default DB path.  Callers that
need transactional grouping should pass an explicit connection.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from jd_matcher.parse.linkedin_email import ParsedPosting

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"


def _open_conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or _DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def is_seen(
    url: str,
    user_id: str = 'default',
    conn: Optional[sqlite3.Connection] = None,
    db_path: Path | None = None,
) -> bool:
    """Return True if (user_id, url) already exists in seen_urls."""
    own_conn = conn is None
    c = conn if conn is not None else _open_conn(db_path)
    try:
        row = c.execute(
            "SELECT 1 FROM seen_urls WHERE user_id = ? AND url = ? LIMIT 1",
            (user_id, url),
        ).fetchone()
        return row is not None
    finally:
        if own_conn:
            c.close()


def mark_seen(
    url: str,
    posting_id: int,
    user_id: str = 'default',
    conn: Optional[sqlite3.Connection] = None,
    db_path: Path | None = None,
) -> None:
    """INSERT a row into seen_urls.

    Raises sqlite3.IntegrityError if (user_id, url) already present.
    Caller is responsible for handling the duplicate-key case.
    """
    own_conn = conn is None
    c = conn if conn is not None else _open_conn(db_path)
    try:
        c.execute(
            """
            INSERT INTO seen_urls (url, user_id, posting_id, seen_at)
            VALUES (?, ?, ?, ?)
            """,
            (url, user_id, posting_id, datetime.now(timezone.utc).isoformat()),
        )
        if own_conn:
            c.commit()
    finally:
        if own_conn:
            c.close()


def register_new(
    parsed: ParsedPosting,
    user_id: str = 'default',
    conn: Optional[sqlite3.Connection] = None,
    db_path: Path | None = None,
) -> tuple[Literal['new', 'seen'], int]:
    """Atomic dedup + insert pipeline.

    If the canonical URL is already in seen_urls → return ('seen', existing_posting_id).
    Otherwise insert into postings, posting_sources, seen_urls within a single
    transaction → return ('new', new_posting_id).

    All three inserts are in one BEGIN/COMMIT block.  Any failure rolls back
    the entire transaction — seen_urls is never written unless the posting was
    successfully created.
    """
    own_conn = conn is None
    c = conn if conn is not None else _open_conn(db_path)
    try:
        with c:
            # Check inside transaction to prevent TOCTOU race.
            existing = c.execute(
                "SELECT posting_id FROM seen_urls WHERE user_id = ? AND url = ? LIMIT 1",
                (user_id, parsed.url),
            ).fetchone()

            if existing:
                return ('seen', existing[0])

            now = datetime.now(timezone.utc).isoformat()
            cursor = c.execute(
                """
                INSERT INTO postings
                    (user_id, canonical_title, canonical_company, canonical_location,
                     hydration_status, first_seen, last_seen)
                VALUES (?, ?, ?, ?, 'partial', ?, ?)
                """,
                (
                    user_id,
                    parsed.title,
                    parsed.company,
                    parsed.location,
                    now,
                    now,
                ),
            )
            posting_id: int = cursor.lastrowid  # type: ignore[assignment]

            source_label = f"{parsed.source}_email"
            raw_body_str = parsed.raw_body.decode('latin-1') if parsed.raw_body else None
            c.execute(
                """
                INSERT INTO posting_sources
                    (posting_id, user_id, source, source_url, source_first_seen, raw_body)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    posting_id,
                    user_id,
                    source_label,
                    parsed.raw_url,
                    parsed.received_at.isoformat(),
                    raw_body_str,
                ),
            )

            c.execute(
                """
                INSERT INTO seen_urls (url, user_id, posting_id, seen_at)
                VALUES (?, ?, ?, ?)
                """,
                (parsed.url, user_id, posting_id, now),
            )

        logger.debug(
            "register_new: new posting_id=%d url=%s source=%s",
            posting_id,
            parsed.url,
            parsed.source,
        )
        return ('new', posting_id)

    finally:
        if own_conn:
            c.close()
