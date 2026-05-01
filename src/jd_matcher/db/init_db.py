"""
Bootstrap the SQLite database for jd-matcher.

init_db() is idempotent — safe to call on every startup.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"


# ---------------------------------------------------------------------------
# Migration registry
#
# Each entry is a 3-tuple:
#   (table_name, column_name, alter_sql)
#
# ``alter_sql`` is the exact ALTER TABLE statement to run if the column is
# absent.  A fourth optional element may be added in future for backfill SQL.
#
# Add new migrations at the END of the list.  Never reorder or remove entries
# (that would break the idempotency invariant on existing databases).
# ---------------------------------------------------------------------------

_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    # M2-010: per-phase stats on pipeline_runs
    (
        "pipeline_runs",
        "counts",
        "ALTER TABLE pipeline_runs ADD COLUMN counts TEXT NULL;",
    ),
    # M2-009/M2-010: separate canonical_seniority on postings
    (
        "postings",
        "canonical_seniority",
        "ALTER TABLE postings ADD COLUMN canonical_seniority TEXT NULL;",
    ),
    # M2-012: JSON context payload on llm_call_ledger
    (
        "llm_call_ledger",
        "notes",
        "ALTER TABLE llm_call_ledger ADD COLUMN notes TEXT NULL;",
    ),
    # M2-013: filter tracking on email_ingest_log
    (
        "email_ingest_log",
        "filter_status",
        "ALTER TABLE email_ingest_log ADD COLUMN filter_status TEXT NULL;",
    ),
    (
        "email_ingest_log",
        "filter_reason",
        "ALTER TABLE email_ingest_log ADD COLUMN filter_reason TEXT NULL;",
    ),
    # M3-001: LLM-extracted classification fields on canonical_postings (C18 v2)
    (
        "canonical_postings",
        "fit_score",
        "ALTER TABLE canonical_postings ADD COLUMN fit_score INTEGER NULL CHECK (fit_score BETWEEN 1 AND 5);",
    ),
    (
        "canonical_postings",
        "fit_reasoning",
        "ALTER TABLE canonical_postings ADD COLUMN fit_reasoning TEXT NULL;",
    ),
    (
        "canonical_postings",
        "industry",
        (
            "ALTER TABLE canonical_postings ADD COLUMN industry TEXT NULL CHECK ("
            "industry IN ("
            "'Financial Services / Asset Management',"
            "'Insurance / Insurtech',"
            "'Telecom / Digital Services',"
            "'Gaming / Entertainment',"
            "'Legal Tech / Compliance',"
            "'Professional Services / Consulting',"
            "'Construction / AEC',"
            "'Energy / Oil & Gas / Cleantech',"
            "'AI Training / Annotation Platforms',"
            "'Staffing / Recruiting',"
            "'AdTech / Marketing Tech',"
            "'B2B SaaS',"
            "'Healthcare / Healthtech',"
            "'Retail / Ecommerce',"
            "'Government / Public Sector / Crown Corp',"
            "'Other'"
            "));"
        ),
    ),
    (
        "canonical_postings",
        "role_orientation",
        # Validated at Pydantic layer (same precedent as top_skills JSON array)
        "ALTER TABLE canonical_postings ADD COLUMN role_orientation TEXT NULL;",
    ),
    (
        "canonical_postings",
        "salary_min_cad",
        "ALTER TABLE canonical_postings ADD COLUMN salary_min_cad INTEGER NULL;",
    ),
    (
        "canonical_postings",
        "salary_max_cad",
        "ALTER TABLE canonical_postings ADD COLUMN salary_max_cad INTEGER NULL;",
    ),
    (
        "canonical_postings",
        "citizenship_requirement",
        (
            "ALTER TABLE canonical_postings ADD COLUMN citizenship_requirement TEXT NULL "
            "CHECK (citizenship_requirement IN ('required', 'preferred', 'not_mentioned'));"
        ),
    ),
    (
        "canonical_postings",
        "citizenship_reason",
        "ALTER TABLE canonical_postings ADD COLUMN citizenship_reason TEXT NULL;",
    ),
    (
        "canonical_postings",
        "can_hire_in_canada",
        (
            "ALTER TABLE canonical_postings ADD COLUMN can_hire_in_canada TEXT NULL "
            "CHECK (can_hire_in_canada IN ('yes', 'likely', 'no', 'unclear'));"
        ),
    ),
    # M3-001: Hard-filter fields on canonical_postings (C33, populated at TASK-M3-006)
    (
        "canonical_postings",
        "is_filtered",
        "ALTER TABLE canonical_postings ADD COLUMN is_filtered BOOLEAN NOT NULL DEFAULT 0;",
    ),
    (
        "canonical_postings",
        "filter_reason",
        "ALTER TABLE canonical_postings ADD COLUMN filter_reason TEXT NULL;",
    ),
]

# Index-only migrations that don't need a column presence check.
# These use CREATE INDEX IF NOT EXISTS which is already idempotent.
_INDEX_MIGRATIONS: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_email_ingest_log_filter ON email_ingest_log (filter_status);",
    # M3-001: leading-prefix index for the C34 4-tuple sort
    # (fit_score DESC, orientation_diversity DESC, salary_max_cad DESC, post_date DESC).
    # orientation_diversity is computed from role_orientation in the query, so the index
    # covers the stored prefix: user_id, fit_score, salary_max_cad.
    (
        "CREATE INDEX IF NOT EXISTS idx_canonical_user_main_rank "
        "ON canonical_postings(user_id, fit_score DESC, salary_max_cad DESC);"
    ),
]


def _apply_pending_migrations(
    conn: sqlite3.Connection,
    migrations: list[tuple[str, str, str]],
) -> None:
    """Apply ALTER TABLE migrations idempotently.

    For each (table, column, sql) entry, skip the ALTER if the column already
    exists (checked via PRAGMA table_info). SQLite does not support
    ADD COLUMN IF NOT EXISTS, so the pre-check is required.

    Args:
        conn:       Open SQLite connection (foreign_keys already set).
        migrations: List of (table_name, column_name, alter_sql) tuples.
    """
    table_columns: dict[str, set[str]] = {}

    for table_name, column_name, alter_sql in migrations:
        if table_name not in table_columns:
            table_columns[table_name] = {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table_name});").fetchall()
            }
        if column_name not in table_columns[table_name]:
            conn.execute(alter_sql)
            # Invalidate cache so subsequent entries on the same table see
            # the freshly added column.
            table_columns.pop(table_name, None)


def init_db(db_path: Optional[Path] = None) -> None:
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
        # via _apply_pending_migrations which checks PRAGMA table_info first.
        _apply_pending_migrations(conn, _COLUMN_MIGRATIONS)
        for index_sql in _INDEX_MIGRATIONS:
            conn.execute(index_sql)
        # Seed the single 'default' user row — ignored if it already exists.
        conn.execute(
            "INSERT OR IGNORE INTO users (id) VALUES (?);",
            ("default",),
        )
        conn.commit()
        logger.debug("init_db: database ready at %s", db_path)
    finally:
        conn.close()
