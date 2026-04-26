"""
Route definitions (C8) — all 9 M1 endpoints.

Endpoint set:
  GET  /                        Main tab (HTML)
  GET  /applied                 Applied tab (HTML)
  GET  /dismissed               Dismissed tab (HTML)
  POST /sync                    Trigger pipeline run
  POST /postings/{id}/apply     State transition → applied
  POST /postings/{id}/dismiss   State transition → dismissed
  POST /postings/{id}/restore   State transition → restore from dismissed
  GET  /healthz                 Liveness check (JSON)
  GET  /api/source-health       Per-source health snapshot (JSON)

B1 guardrail: GmailIngester writes pipeline_runs rows with the same `source`
value as the orchestrator (gmail_linkedin / gmail_indeed) but its run_ids carry
the substring '_ingest_'.  The /api/source-health query filters to canonical
orchestrator rows via: run_id NOT LIKE '%_ingest_%'.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from jd_matcher.db.init_db import init_db
from jd_matcher.state.manager import (
    dismiss,
    main_view_postings,
    mark_applied,
    restore,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"

# The four canonical source names registered by M1.
_CANONICAL_SOURCES = [
    "gmail_linkedin",
    "gmail_indeed",
    "hydrator_linkedin",
    "hydrator_indeed",
]


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class PostingActionResponse(BaseModel):
    posting_id: int
    action: str
    status: str


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_db_path() -> Path:
    env_val = os.environ.get("JD_MATCHER_DB_PATH")
    if env_val:
        return Path(env_val)
    return _DEFAULT_DB_PATH


def _open_conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _ensure_db(db_path: Path) -> None:
    init_db(db_path)


def _get_applied_postings(
    conn: sqlite3.Connection, user_id: str = "default"
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.id, p.canonical_title, p.canonical_company, p.canonical_location,
               p.hydration_status, p.first_seen, p.last_seen,
               a.status, a.applied_at, a.status_updated_at, a.notes
        FROM postings p
        JOIN applied a ON a.posting_id = p.id AND a.user_id = p.user_id
        WHERE p.user_id = ?
        ORDER BY a.applied_at DESC
        """,
        (user_id,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "canonical_title": r[1],
            "canonical_company": r[2],
            "canonical_location": r[3],
            "hydration_status": r[4],
            "first_seen": r[5],
            "last_seen": r[6],
            "status": r[7],
            "applied_at": r[8],
            "status_updated_at": r[9],
            "notes": r[10],
        }
        for r in rows
    ]


def _get_dismissed_postings(
    conn: sqlite3.Connection, user_id: str = "default"
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.id, p.canonical_title, p.canonical_company, p.canonical_location,
               p.hydration_status, p.first_seen, p.last_seen,
               d.dismissed_at
        FROM postings p
        JOIN dismissed d ON d.posting_id = p.id AND d.user_id = p.user_id
        WHERE p.user_id = ?
        ORDER BY d.dismissed_at DESC
        """,
        (user_id,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "canonical_title": r[1],
            "canonical_company": r[2],
            "canonical_location": r[3],
            "hydration_status": r[4],
            "first_seen": r[5],
            "last_seen": r[6],
            "dismissed_at": r[7],
        }
        for r in rows
    ]


def _source_health_query(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return one health entry per canonical source.

    B1 guardrail: filters to orchestrator-canonical rows only by excluding
    rows whose run_id contains '_ingest_' (the sub-run ID pattern used by
    GmailIngester).  Both the orchestrator and the ingester write rows with
    the same `source` value, so we cannot use source-level filtering alone.
    """
    entries = []
    for source in _CANONICAL_SOURCES:
        row = conn.execute(
            """
            SELECT
                health_status,
                failure_reason,
                started_at,
                (
                    SELECT started_at
                    FROM pipeline_runs p2
                    WHERE p2.source = pr.source
                      AND p2.health_status = 'healthy'
                      AND p2.run_id NOT LIKE '%_ingest_%'
                    ORDER BY p2.started_at DESC
                    LIMIT 1
                ) AS last_successful_fetch_at
            FROM pipeline_runs pr
            WHERE pr.source = ?
              AND pr.run_id NOT LIKE '%_ingest_%'
            ORDER BY pr.started_at DESC
            LIMIT 1
            """,
            (source,),
        ).fetchone()

        if row is None:
            entries.append(
                {
                    "source": source,
                    "health_status": "never_run",
                    "last_run": None,
                    "last_successful_fetch_at": None,
                    "failure_reason": None,
                }
            )
        else:
            entries.append(
                {
                    "source": source,
                    "health_status": row[0],
                    "last_run": row[2],
                    "last_successful_fetch_at": row[3],
                    "failure_reason": row[1],
                }
            )
    return entries


def _main_view_postings_list(
    conn: sqlite3.Connection, user_id: str = "default"
) -> list[dict[str, Any]]:
    """All postings not in applied or dismissed — NO hydration_status filter."""
    postings = main_view_postings(user_id=user_id, conn=conn)
    return [
        {
            "id": p.id,
            "canonical_title": p.canonical_title,
            "canonical_company": p.canonical_company,
            "canonical_location": p.canonical_location,
            "hydration_status": p.hydration_status,
            "first_seen": p.first_seen,
            "last_seen": p.last_seen,
        }
        for p in postings
    ]


# ---------------------------------------------------------------------------
# HTML tab endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def main_tab(request: Request) -> HTMLResponse:
    db_path = _get_db_path()
    _ensure_db(db_path)
    conn = _open_conn(db_path)
    try:
        postings = _main_view_postings_list(conn)
        count = len(postings)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "main.html",
        {"postings": postings, "count": count},
    )


@router.get("/applied", response_class=HTMLResponse)
async def applied_tab(request: Request) -> HTMLResponse:
    db_path = _get_db_path()
    _ensure_db(db_path)
    conn = _open_conn(db_path)
    try:
        postings = _get_applied_postings(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "applied.html",
        {"postings": postings},
    )


@router.get("/dismissed", response_class=HTMLResponse)
async def dismissed_tab(request: Request) -> HTMLResponse:
    db_path = _get_db_path()
    _ensure_db(db_path)
    conn = _open_conn(db_path)
    try:
        postings = _get_dismissed_postings(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "dismissed.html",
        {"postings": postings},
    )


# ---------------------------------------------------------------------------
# Pipeline trigger
# ---------------------------------------------------------------------------


@router.post("/sync")
async def sync(request: Request) -> JSONResponse:
    """Trigger a full pipeline run.

    Returns JSON with the run summary.  A real run requires OAuth credentials;
    in SKIP_LIVE=1 mode the pipeline runs against fixtures.
    """
    from jd_matcher.pipeline import run_pipeline

    db_path = _get_db_path()
    try:
        summary = run_pipeline(db_path=db_path)
        return JSONResponse(
            {
                "run_id": summary.run_id,
                "total_new_postings": summary.total_new_postings,
                "failed_sources": summary.failed_sources,
                "started_at": summary.started_at.isoformat(),
                "finished_at": summary.finished_at.isoformat(),
            }
        )
    except Exception as exc:
        logger.error("Pipeline sync failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# State-mutation endpoints
# ---------------------------------------------------------------------------


@router.post("/postings/{posting_id}/apply")
async def apply_posting(posting_id: int) -> JSONResponse:
    db_path = _get_db_path()
    _ensure_db(db_path)
    conn = _open_conn(db_path)
    try:
        mark_applied(posting_id, conn=conn)
        conn.commit()
    finally:
        conn.close()

    return JSONResponse(
        PostingActionResponse(
            posting_id=posting_id, action="apply", status="ok"
        ).model_dump(),
        status_code=200,
    )


@router.post("/postings/{posting_id}/dismiss")
async def dismiss_posting(posting_id: int) -> JSONResponse:
    db_path = _get_db_path()
    _ensure_db(db_path)
    conn = _open_conn(db_path)
    try:
        dismiss(posting_id, conn=conn)
        conn.commit()
    finally:
        conn.close()

    return JSONResponse(
        PostingActionResponse(
            posting_id=posting_id, action="dismiss", status="ok"
        ).model_dump(),
        status_code=200,
    )


@router.post("/postings/{posting_id}/restore")
async def restore_posting(posting_id: int) -> JSONResponse:
    db_path = _get_db_path()
    _ensure_db(db_path)
    conn = _open_conn(db_path)
    try:
        restore(posting_id, conn=conn)
        conn.commit()
    finally:
        conn.close()

    return JSONResponse(
        PostingActionResponse(
            posting_id=posting_id, action="restore", status="ok"
        ).model_dump(),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Health + source-health endpoints
# ---------------------------------------------------------------------------


@router.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


@router.get("/api/source-health")
async def source_health() -> JSONResponse:
    db_path = _get_db_path()
    _ensure_db(db_path)
    conn = _open_conn(db_path)
    try:
        entries = _source_health_query(conn)
    finally:
        conn.close()

    return JSONResponse(entries)
