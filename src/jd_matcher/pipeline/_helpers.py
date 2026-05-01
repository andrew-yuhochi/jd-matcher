"""
Pipeline DB utility helpers shared across the orchestrator and phase modules.

Extracted from pipeline/__init__.py (TASK-M3-000b) to bring the orchestrator
under 300 lines without losing any functionality.
"""

from __future__ import annotations

import json
import logging
import logging.config
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "jd_matcher.pipeline"
logger = logging.getLogger(_LOGGER_NAME)

# ---------------------------------------------------------------------------
# Structured JSON log setup
# ---------------------------------------------------------------------------


def setup_run_logger(run_id: str, logs_dir: Path | None = None) -> Path:
    """Create a per-run JSONL log file and attach a handler to the pipeline logger.

    Args:
        run_id:   Unique run identifier; used in the log filename.
        logs_dir: Override directory for log files. Defaults to
                  <project-root>/logs/ resolved relative to this file.
                  Exposed as a parameter so callers can monkeypatch in tests
                  without touching internal module state.
    """
    _default_logs_dir = Path(__file__).parents[3] / "logs"
    effective_logs_dir = logs_dir if logs_dir is not None else _default_logs_dir
    effective_logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = effective_logs_dir / f"pipeline-{run_id}.jsonl"

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    class _PassthroughFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            return record.getMessage()

    file_handler.setFormatter(_PassthroughFormatter())

    pipeline_logger = logging.getLogger(_LOGGER_NAME)
    pipeline_logger.addHandler(file_handler)
    pipeline_logger.setLevel(logging.DEBUG)

    return log_path


# ---------------------------------------------------------------------------
# pipeline_runs table writes
# ---------------------------------------------------------------------------


def write_pipeline_run(
    db_path: Path,
    *,
    run_id: str,
    source: str,
    health_status: str,
    failure_reason: Optional[str],
    started_at: datetime,
    finished_at: datetime,
    last_successful_fetch_at: Optional[datetime],
    counts: Optional[dict] = None,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        counts_json = json.dumps(counts) if counts else None
        conn.execute(
            """
            INSERT INTO pipeline_runs
                (run_id, source, health_status, failure_reason,
                 started_at, finished_at, last_successful_fetch_at, counts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source,
                health_status,
                failure_reason,
                started_at.isoformat(),
                finished_at.isoformat(),
                last_successful_fetch_at.isoformat() if last_successful_fetch_at else None,
                counts_json,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_previous_status(db_path: Path, source: str) -> str:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT health_status FROM pipeline_runs
            WHERE source = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (source,),
        ).fetchone()
        return row[0] if row else "never_run"
    finally:
        conn.close()


def last_successful_fetch_at(db_path: Path, source: str) -> Optional[datetime]:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT last_successful_fetch_at FROM pipeline_runs
            WHERE source = ? AND health_status = 'healthy'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (source,),
        ).fetchone()
        if row and row[0]:
            return datetime.fromisoformat(row[0])
        return None
    finally:
        conn.close()


def emit_transition_event_if_needed(
    db_path: Path,
    source: str,
    previous_status: str,
    new_status: str,
    failure_reason: Optional[str],
    run_id: str,
) -> None:
    is_bad = new_status in ("degraded", "failed")
    was_ok = previous_status in ("healthy", "never_run")
    if not (is_bad and was_ok):
        return

    now = datetime.now(timezone.utc)
    metadata = json.dumps({
        "source": source,
        "previous_status": previous_status,
        "new_status": new_status,
        "failure_reason": failure_reason,
        "run_id": run_id,
    })

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO events (user_id, event_type, metadata, timestamp)
            VALUES ('default', 'source_failure', ?, ?)
            """,
            (metadata, now.isoformat()),
        )
        conn.commit()
        logger.warning(
            json.dumps({
                "event": "source_failure_transition",
                "source": source,
                "previous_status": previous_status,
                "new_status": new_status,
                "failure_reason": failure_reason,
                "run_id": run_id,
            })
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Posting / embedding / ledger DB queries
# ---------------------------------------------------------------------------


def get_pending_hydration_urls(db_path: Path, sender: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT su.url
            FROM seen_urls su
            JOIN postings p ON su.posting_id = p.id
            WHERE su.url LIKE ?
              AND p.hydration_status IN ('partial', 'failed')
            LIMIT 200
            """,
            (f"%{sender}.com%" if sender == "linkedin" else f"%indeed.com%",),
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def get_pending_extraction_ids(db_path: Path) -> list[int]:
    conn = sqlite3.connect(db_path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(postings)").fetchall()}
        if "extraction_status" not in cols:
            rows = conn.execute(
                """
                SELECT id FROM postings
                WHERE full_jd IS NOT NULL AND full_jd != ''
                ORDER BY id
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id FROM postings
                WHERE full_jd IS NOT NULL AND full_jd != ''
                  AND (extraction_status IS NULL OR extraction_status != 'success')
                ORDER BY id
                """
            ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def get_pending_embedding_ids(db_path: Path) -> list[int]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT p.id
            FROM postings p
            WHERE p.id NOT IN (
                SELECT CAST(pe.posting_id AS INTEGER)
                FROM posting_embeddings pe
                WHERE pe.model_name = 'text-embedding-3-small'
            )
              AND (p.role_summary IS NOT NULL OR p.full_jd IS NOT NULL)
            ORDER BY p.id
            """
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def get_embedded_posting_ids(db_path: Path) -> list[int]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT CAST(posting_id AS INTEGER) FROM posting_embeddings ORDER BY posting_id"
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def get_already_linked_posting_ids(db_path: Path) -> set[int]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT CAST(posting_id AS INTEGER) FROM posting_canonical_links"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def get_max_ledger_id(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM llm_call_ledger"
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def ledger_delta(db_path: Path, call_kind: str, before_id: int) -> dict:
    """Return {count, cache_hits, cost_usd} for ledger rows with call_kind after before_id."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'cache_hit' THEN 1 ELSE 0 END) AS cache_hits,
                COALESCE(SUM(cost_usd), 0.0) AS cost_usd
            FROM llm_call_ledger
            WHERE call_kind = ?
              AND id > ?
            """,
            (call_kind, before_id),
        ).fetchone()
        if row is None:
            return {"count": 0, "cache_hits": 0, "cost_usd": 0.0}
        return {
            "count": row[0] or 0,
            "cache_hits": row[1] or 0,
            "cost_usd": float(row[2] or 0.0),
        }
    finally:
        conn.close()


def fetch_posting_row(db_path: Path, posting_id: int) -> "PostingRow | None":
    from jd_matcher.llm.extract import PostingRow

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT id, full_jd, canonical_title, canonical_company, canonical_location
            FROM postings
            WHERE id = ?
            """,
            (posting_id,),
        ).fetchone()
        if row is None:
            return None
        return PostingRow(
            id=row[0],
            full_jd=row[1] or "",
            canonical_title=row[2],
            canonical_company=row[3],
            canonical_location=row[4],
        )
    finally:
        conn.close()


def get_monthly_llm_cost(db_path: Path) -> float:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(cost_usd), 0.0)
            FROM llm_call_ledger
            WHERE DATE(called_at) >= DATE('now', 'start of month')
            """
        ).fetchone()
        return float(row[0]) if row else 0.0
    finally:
        conn.close()
