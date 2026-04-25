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
        # SQLite disables foreign-key enforcement by default; enable it for
        # every connection so constraints are actually checked at runtime.
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_sql)
        # Seed the single 'default' user row — ignored if it already exists.
        conn.execute(
            "INSERT OR IGNORE INTO users (id) VALUES (?);",
            ("default",),
        )
        conn.commit()
        logger.debug("init_db: database ready at %s", db_path)
    finally:
        conn.close()
