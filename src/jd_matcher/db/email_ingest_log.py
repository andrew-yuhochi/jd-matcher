"""
email_ingest_log DB helpers (C3/C4/C5 writer hooks).

All three writer hooks operate on the same table:
  - C3 (insert_email_log):     inserts one row per fetched email, counters=0
  - C4 (update_url_counts):    updates urls_extracted_count / urls_new_count
  - C5 (increment_hydration):  atomically increments hydration counters per outcome

All writes use the canonical orchestrator pipeline_run_id, never a sub-run id.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"


def _open(db_path: Path | None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or _DEFAULT_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ---------------------------------------------------------------------------
# C3 writer — one row per fetched email
# ---------------------------------------------------------------------------


def insert_email_log(
    *,
    gmail_message_id: str,
    source: str,
    sender: str,
    subject: str,
    received_at: datetime,
    pipeline_run_id: str,
    db_path: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Insert one row into email_ingest_log for a newly fetched email.

    Uses INSERT OR REPLACE so re-syncing the same Gmail message updates the row's
    pipeline_run_id and ingested_at to the most-recent orchestrator run.  This
    prevents orphan rows (from diagnostic or manual fetches) from permanently
    attributing an email to a stale run_id — the report always shows the latest
    sync's emails.
    """
    own = conn is None
    c = conn if conn is not None else _open(db_path)
    now = datetime.now(timezone.utc).isoformat()
    try:
        c.execute(
            """
            INSERT OR REPLACE INTO email_ingest_log
                (gmail_message_id, source, sender, subject, received_at,
                 ingested_at, pipeline_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                gmail_message_id,
                source,
                sender,
                subject,
                received_at.isoformat() if isinstance(received_at, datetime) else received_at,
                now,
                pipeline_run_id,
            ),
        )
        if own:
            c.commit()
        logger.debug(
            "email_ingest_log: inserted gmail_message_id=%s source=%s run_id=%s",
            gmail_message_id,
            source,
            pipeline_run_id,
        )
    finally:
        if own:
            c.close()


# ---------------------------------------------------------------------------
# C4 writer — update URL counts after parsing
# ---------------------------------------------------------------------------


def update_url_counts(
    *,
    gmail_message_id: str,
    urls_extracted_count: int,
    urls_new_count: int,
    postings_created_count: int = 0,
    db_path: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Set URL counters on the email_ingest_log row identified by gmail_message_id.

    Called by C4 after URL dedup completes for one email.
    """
    own = conn is None
    c = conn if conn is not None else _open(db_path)
    try:
        c.execute(
            """
            UPDATE email_ingest_log
            SET urls_extracted_count = ?,
                urls_new_count       = ?,
                postings_created_count = ?
            WHERE gmail_message_id   = ?
            """,
            (urls_extracted_count, urls_new_count, postings_created_count, gmail_message_id),
        )
        if own:
            c.commit()
        logger.debug(
            "email_ingest_log: updated url counts for gmail_message_id=%s "
            "extracted=%d new=%d created=%d",
            gmail_message_id,
            urls_extracted_count,
            urls_new_count,
            postings_created_count,
        )
    finally:
        if own:
            c.close()


# ---------------------------------------------------------------------------
# C5 writer — per-posting hydration outcome accumulator
# ---------------------------------------------------------------------------


def increment_hydration(
    *,
    gmail_message_id: str,
    success: bool,
    db_path: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Atomically increment hydration counters for one posting outcome.

    Called once per posting by C5. Multiple postings from the same email
    each call this function, accumulating into the same row.
    """
    own = conn is None
    c = conn if conn is not None else _open(db_path)
    try:
        if success:
            c.execute(
                """
                UPDATE email_ingest_log
                SET postings_hydrated_count = postings_hydrated_count + 1
                WHERE gmail_message_id = ?
                """,
                (gmail_message_id,),
            )
        else:
            c.execute(
                """
                UPDATE email_ingest_log
                SET postings_hydration_failed_count = postings_hydration_failed_count + 1
                WHERE gmail_message_id = ?
                """,
                (gmail_message_id,),
            )
        if own:
            c.commit()
        logger.debug(
            "email_ingest_log: hydration outcome success=%s for gmail_message_id=%s",
            success,
            gmail_message_id,
        )
    finally:
        if own:
            c.close()


# ---------------------------------------------------------------------------
# Report query
# ---------------------------------------------------------------------------


def query_email_ingest_log(
    *,
    since: str | None = None,
    source: str | None = None,
    db_path: Path | None = None,
) -> list[dict]:
    """Return email_ingest_log rows as dicts, optionally filtered.

    Args:
        since:   ISO date string YYYY-MM-DD; filters received_at >= since.
        source:  Filter by source column (e.g. "linkedin", "indeed").
        db_path: Path to SQLite DB.

    Returns:
        List of row dicts ordered by received_at DESC.
    """
    c = _open(db_path)
    try:
        clauses: list[str] = []
        params: list[str] = []
        if since:
            clauses.append("received_at >= ?")
            params.append(since)
        if source:
            clauses.append("source = ?")
            params.append(source)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = c.execute(
            f"""
            SELECT
                gmail_message_id,
                source,
                sender,
                subject,
                received_at,
                ingested_at,
                pipeline_run_id,
                urls_extracted_count,
                urls_new_count,
                postings_created_count,
                postings_hydrated_count,
                postings_hydration_failed_count,
                notes
            FROM email_ingest_log
            {where}
            ORDER BY received_at DESC
            """,
            params,
        ).fetchall()

        columns = [
            "gmail_message_id",
            "source",
            "sender",
            "subject",
            "received_at",
            "ingested_at",
            "pipeline_run_id",
            "urls_extracted_count",
            "urls_new_count",
            "postings_created_count",
            "postings_hydrated_count",
            "postings_hydration_failed_count",
            "notes",
        ]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        c.close()
