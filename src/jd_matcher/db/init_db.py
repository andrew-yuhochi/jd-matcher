"""
Bootstrap the SQLite database for jd-matcher.

init_db() is idempotent — safe to call on every startup.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"


def _ensure_pipeline_runs_counts_column(conn: sqlite3.Connection) -> None:
    """Add counts column to pipeline_runs if absent (M2-010 migration).

    Stores per-phase stats (e.g. extraction cost, embedding batch counts) as JSON.
    SQLite lacks ADD COLUMN IF NOT EXISTS — check PRAGMA table_info first.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs);")}
    if "counts" not in existing:
        conn.execute("ALTER TABLE pipeline_runs ADD COLUMN counts TEXT NULL;")


def _ensure_postings_canonical_seniority_column(conn: sqlite3.Connection) -> None:
    """Add canonical_seniority column to postings if absent (M2-009/M2-010 migration).

    M2-009 merge.py references canonical_seniority but existing DBs created
    before M2-009 only have seniority_band.  Adding canonical_seniority as a
    separate nullable column (rather than renaming) avoids DROP+CREATE complexity
    and keeps historical seniority_band data intact.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(postings);")}
    if "canonical_seniority" not in existing:
        conn.execute("ALTER TABLE postings ADD COLUMN canonical_seniority TEXT NULL;")


def _ensure_email_ingest_log_filter_columns(conn: sqlite3.Connection) -> None:
    """Add filter_status / filter_reason columns + their index to email_ingest_log if absent.

    SQLite has no ADD COLUMN IF NOT EXISTS syntax, so we inspect PRAGMA
    table_info before issuing each ALTER TABLE to keep init_db() idempotent.
    The index on filter_status is also created here (not in schema.sql) because
    executescript runs before the ALTER, so the column doesn't exist yet when
    schema.sql is executed on a fresh DB.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(email_ingest_log);")}
    if "filter_status" not in existing:
        conn.execute("ALTER TABLE email_ingest_log ADD COLUMN filter_status TEXT NULL;")
    if "filter_reason" not in existing:
        conn.execute("ALTER TABLE email_ingest_log ADD COLUMN filter_reason TEXT NULL;")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_ingest_log_filter "
        "ON email_ingest_log (filter_status);"
    )


def init_db(db_path: Path | None = None) -> None:
    """Create the database and apply schema.sql if it has not been applied yet.

    Args:
        db_path: Filesystem path for the SQLite file.  Defaults to
                 ``~/.jd-matcher/jd-matcher.db``.  The parent directory is
                 created automatically if it does not exist.
    """
    if db_path is None:
        db_path = _DEFAULT_DB_PATH

    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")

    conn = sqlite3.connect(db_path)
    try:
        # WAL mode allows concurrent readers + 1 writer, eliminating the
        # lock contention between the hydrator's write transactions and the
        # web UI's read transactions (the default rollback-journal mode
        # blocks readers while a writer holds the lock).
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")  # safe with WAL, faster than FULL
        # SQLite disables foreign-key enforcement by default; enable it for
        # every connection so constraints are actually checked at runtime.
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_sql)
        # ALTER TABLE statements cannot use IF NOT EXISTS in SQLite; apply them
        # via a Python helper that checks PRAGMA table_info first.
        _ensure_pipeline_runs_counts_column(conn)
        _ensure_postings_canonical_seniority_column(conn)
        _ensure_email_ingest_log_filter_columns(conn)
        # Seed the single 'default' user row — ignored if it already exists.
        conn.execute(
            "INSERT OR IGNORE INTO users (id) VALUES (?);",
            ("default",),
        )
        conn.commit()
        logger.debug("init_db: database ready at %s", db_path)
    finally:
        conn.close()
