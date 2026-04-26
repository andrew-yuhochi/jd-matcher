"""
Pipeline orchestrator (C11) — sequences per-source ingestion, parsing, dedup, and hydration.

Sources (M1):
  gmail_linkedin   — Gmail fetch + LinkedIn email parse + URL dedup
  gmail_indeed     — Gmail fetch + Indeed email parse + URL dedup
  hydrator_linkedin — LinkedIn JD hydration for deduped postings
  hydrator_indeed   — Indeed JD hydration for deduped postings

Per-source isolation invariant: one source failing CANNOT cascade to others.
Mandatory persistence invariant: regardless of outcome, exactly one pipeline_runs
row is written per source per run with non-null health_status.

Drift decisions (relative to TDD §C11):
  - Log path: uses logs/pipeline-<run_id>.jsonl (project-relative, per-run file)
    rather than ~/.jd-matcher/logs/jd-matcher.log (rolling). TASKS.md ACs take
    precedence; architect to reconcile at MVP.
  - C10 (events emitter): C10 has no implementation in M1; this module writes
    source_failure events directly to the events table. Document as M1 simplification.
"""

from __future__ import annotations

import json
import logging
import logging.config
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from jd_matcher.db.email_ingest_log import increment_hydration, update_url_counts
from jd_matcher.db.init_db import init_db
from jd_matcher.dedup.url_dedup import register_new
from jd_matcher.hydrate import compute_source_health
from jd_matcher.hydrate.indeed import hydrate as indeed_hydrate
from jd_matcher.hydrate.linkedin import hydrate as linkedin_hydrate
from jd_matcher.ingest.gmail import GmailIngester
from jd_matcher.parse.indeed_email import parse as parse_indeed
from jd_matcher.parse.linkedin_email import ParsedPosting, parse as parse_linkedin

_LOGGER_NAME = "jd_matcher.pipeline"
logger = logging.getLogger(_LOGGER_NAME)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"
# parents[2] = projects/jd-matcher/ (one above src/)
_LOGS_DIR = Path(__file__).parents[2] / "logs"

# M1 sources in execution order
_GMAIL_SOURCES = ("linkedin", "indeed")
_HYDRATOR_SOURCES = ("linkedin", "indeed")

_STEP_LABELS = [
    "Fetching Gmail (linkedin)… (1/4)",
    "Fetching Gmail (indeed)… (2/4)",
    "Hydrating JDs (linkedin)… (3/4)",
    "Hydrating JDs (indeed)… (4/4)",
]


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


@dataclass
class SourceResult:
    source: str
    health_status: str
    failure_reason: Optional[str] = None
    new_postings: int = 0
    hydrated: int = 0
    # All postings parsed during the Gmail phase; each carries its own gmail_message_id.
    postings: list[ParsedPosting] = field(default_factory=list)


@dataclass
class PipelineRunSummary:
    run_id: str
    started_at: datetime
    finished_at: datetime
    sources: list[SourceResult]
    steps: list[str]
    total_new_postings: int

    @property
    def failed_sources(self) -> list[str]:
        return [s.source for s in self.sources if s.health_status != "healthy"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pipeline(
    db_path: Optional[Path] = None,
    credentials: object = None,
    since_days: int = 2,
) -> PipelineRunSummary:
    """Run the full M1 pipeline for all four sources.

    Args:
        db_path:     Path to SQLite DB; defaults to ~/.jd-matcher/jd-matcher.db.
        credentials: Google OAuth credentials object (None when SKIP_LIVE=1).
        since_days:  How many days of email history to fetch.

    Returns:
        PipelineRunSummary with per-source health and aggregate counts.
    """
    resolved_db = db_path or _DEFAULT_DB_PATH
    init_db(resolved_db)

    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)

    log_path = _setup_run_logger(run_id)

    logger.info(
        json.dumps({
            "event": "pipeline_start",
            "run_id": run_id,
            "started_at": started_at.isoformat(),
        })
    )

    source_results: list[SourceResult] = []
    steps_emitted: list[str] = []

    # -----------------------------------------------------------------------
    # Phase 1: Gmail ingestion + parsing + URL dedup
    # -----------------------------------------------------------------------
    for i, sender in enumerate(_GMAIL_SOURCES):
        source_name = f"gmail_{sender}"
        step_label = f"Fetching Gmail ({sender})… ({i + 1}/4)"
        steps_emitted.append(step_label)

        result = _run_gmail_source(
            source_name=source_name,
            sender=sender,
            run_id=run_id,
            resolved_db=resolved_db,
            credentials=credentials,
            since_days=since_days,
        )
        source_results.append(result)

        logger.info(
            json.dumps({
                "event": "source_complete",
                "run_id": run_id,
                "source": source_name,
                "health_status": result.health_status,
                "new_postings": result.new_postings,
                "step": step_label,
            })
        )

    # Collect all postings from Gmail phase; first-email-wins for duplicate URLs.
    # Each ParsedPosting carries its own gmail_message_id — no side-mapping needed.
    all_postings: list[ParsedPosting] = []
    for gmail_result in source_results:
        all_postings.extend(gmail_result.postings)

    # Collect canonical URLs for hydration — query DB after dedup so we only
    # hydrate postings that were actually registered (dedup-respected).
    li_urls = _get_pending_hydration_urls(resolved_db, "linkedin")
    in_urls = _get_pending_hydration_urls(resolved_db, "indeed")
    hydration_urls = {"linkedin": li_urls, "indeed": in_urls}

    # -----------------------------------------------------------------------
    # Phase 2: Hydration
    # -----------------------------------------------------------------------
    for i, sender in enumerate(_HYDRATOR_SOURCES):
        source_name = f"hydrator_{sender}"
        step_label = f"Hydrating JDs ({sender})… ({i + 3}/4)"
        steps_emitted.append(step_label)

        result = _run_hydrator_source(
            source_name=source_name,
            sender=sender,
            run_id=run_id,
            resolved_db=resolved_db,
            urls=hydration_urls.get(sender, []),
            all_postings=all_postings,
        )
        source_results.append(result)

        logger.info(
            json.dumps({
                "event": "source_complete",
                "run_id": run_id,
                "source": source_name,
                "health_status": result.health_status,
                "hydrated": result.hydrated,
                "step": step_label,
            })
        )

    finished_at = datetime.now(timezone.utc)
    total_new = sum(r.new_postings for r in source_results)

    summary = PipelineRunSummary(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        sources=source_results,
        steps=steps_emitted,
        total_new_postings=total_new,
    )

    logger.info(
        json.dumps({
            "event": "pipeline_complete",
            "run_id": run_id,
            "finished_at": finished_at.isoformat(),
            "total_new_postings": total_new,
            "failed_sources": summary.failed_sources,
            "log_path": str(log_path),
        })
    )

    return summary


# ---------------------------------------------------------------------------
# Per-source runners with mandatory-persistence wrappers
# ---------------------------------------------------------------------------


def _run_gmail_source(
    *,
    source_name: str,
    sender: str,
    run_id: str,
    resolved_db: Path,
    credentials: object,
    since_days: int,
) -> SourceResult:
    """Fetch Gmail + parse + dedup for one sender. ALWAYS writes pipeline_runs row.

    The orchestrator is the single writer of the canonical pipeline_runs row for
    this source+run_id.  GmailIngester.fetch_for_sender is called with a sub-run
    ID so its internal writes do not conflict with the orchestrator's row.
    """
    started_at = datetime.now(timezone.utc)
    prev_status = _get_previous_status(resolved_db, source_name)

    # Sub-run ID keeps ingester's internal pipeline_runs rows separate from the
    # orchestrator's canonical row for this source.
    ingester_run_id = f"{run_id}_ingest_{sender}"

    try:
        since_date = datetime.now(timezone.utc) - timedelta(days=since_days)

        ingester = GmailIngester(credentials=credentials, db_path=resolved_db)
        emails = ingester.fetch_for_sender(
            sender,
            since_date,
            run_id=ingester_run_id,
            canonical_run_id=run_id,
        )

        new_urls: list[str] = []
        parsed_postings: list[ParsedPosting] = []
        parser = parse_linkedin if sender == "linkedin" else parse_indeed
        conn = sqlite3.connect(resolved_db)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            for raw_email in emails:
                postings = parser(raw_email)
                parsed_postings.extend(postings)
                urls_extracted = len(postings)
                urls_new = 0
                urls_created = 0
                for posting in postings:
                    outcome, _ = register_new(posting, conn=conn, db_path=resolved_db)
                    if outcome == "new":
                        new_urls.append(posting.url)
                        urls_new += 1
                        urls_created += 1

                # C4 writer hook — update URL counts for this email's row.
                try:
                    update_url_counts(
                        gmail_message_id=raw_email.id,
                        urls_extracted_count=urls_extracted,
                        urls_new_count=urls_new,
                        postings_created_count=urls_created,
                        db_path=resolved_db,
                        conn=conn,
                    )
                except Exception:
                    logger.warning(
                        "C4 update_url_counts failed for gmail_message_id=%s",
                        raw_email.id,
                        exc_info=True,
                    )

            conn.commit()
        finally:
            conn.close()

        finished_at = datetime.now(timezone.utc)
        last_successful = started_at
        _write_pipeline_run(
            resolved_db,
            run_id=run_id,
            source=source_name,
            health_status="healthy",
            failure_reason=None,
            started_at=started_at,
            finished_at=finished_at,
            last_successful_fetch_at=last_successful,
        )
        _emit_transition_event_if_needed(
            resolved_db, source_name, prev_status, "healthy", None, run_id
        )

        logger.info(
            json.dumps({
                "event": "gmail_source_step",
                "run_id": run_id,
                "source": source_name,
                "emails_fetched": len(emails),
                "new_postings": len(new_urls),
                "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
            })
        )

        return SourceResult(
            source=source_name,
            health_status="healthy",
            new_postings=len(new_urls),
            postings=parsed_postings,
        )

    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        failure_reason = f"{type(exc).__name__}: {exc}"
        logger.error(
            json.dumps({
                "event": "gmail_source_failed",
                "run_id": run_id,
                "source": source_name,
                "failure_reason": failure_reason,
                "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
            })
        )

        last_successful = _last_successful_fetch_at(resolved_db, source_name)
        _write_pipeline_run(
            resolved_db,
            run_id=run_id,
            source=source_name,
            health_status="failed",
            failure_reason=failure_reason,
            started_at=started_at,
            finished_at=finished_at,
            last_successful_fetch_at=last_successful,
        )
        _emit_transition_event_if_needed(
            resolved_db, source_name, prev_status, "failed", failure_reason, run_id
        )

        return SourceResult(
            source=source_name,
            health_status="failed",
            failure_reason=failure_reason,
        )


def _run_hydrator_source(
    *,
    source_name: str,
    sender: str,
    run_id: str,
    resolved_db: Path,
    urls: list[str],
    all_postings: list[ParsedPosting] | None = None,
) -> SourceResult:
    """Hydrate all pending JDs for one sender. ALWAYS writes pipeline_runs row.

    gmail_message_id is read directly from each ParsedPosting — no side-mapping dict.
    First-email-wins: when the same URL appears in multiple emails, only the first
    ParsedPosting's gmail_message_id is used for hydration credit attribution.
    """
    started_at = datetime.now(timezone.utc)
    prev_status = _get_previous_status(resolved_db, source_name)

    # Build url → gmail_message_id from postings (first-email-wins).
    url_to_gmail_id: dict[str, str] = {}
    for posting in (all_postings or []):
        if posting.url not in url_to_gmail_id:
            url_to_gmail_id[posting.url] = posting.gmail_message_id

    try:
        hydrate_fn = linkedin_hydrate if sender == "linkedin" else indeed_hydrate
        results = []
        for url in urls:
            jd = hydrate_fn(url)
            results.append(jd)
            _update_posting_hydration(resolved_db, url, jd)

            # C5 writer hook — increment hydration counter on the originating email row.
            gmail_id = url_to_gmail_id.get(url)
            if gmail_id:
                try:
                    success = getattr(jd, "hydration_status", "failed") in ("complete", "partial")
                    increment_hydration(
                        gmail_message_id=gmail_id,
                        success=success,
                        db_path=resolved_db,
                    )
                except Exception:
                    logger.warning(
                        "C5 increment_hydration failed for gmail_message_id=%s url=%s",
                        gmail_id,
                        url,
                        exc_info=True,
                    )

        health_status, failure_reason = compute_source_health(results)  # type: ignore[arg-type]

        finished_at = datetime.now(timezone.utc)
        last_successful = started_at if health_status == "healthy" else _last_successful_fetch_at(resolved_db, source_name)
        _write_pipeline_run(
            resolved_db,
            run_id=run_id,
            source=source_name,
            health_status=health_status,
            failure_reason=failure_reason,
            started_at=started_at,
            finished_at=finished_at,
            last_successful_fetch_at=last_successful,
        )
        _emit_transition_event_if_needed(
            resolved_db, source_name, prev_status, health_status, failure_reason, run_id
        )

        logger.info(
            json.dumps({
                "event": "hydrator_source_step",
                "run_id": run_id,
                "source": source_name,
                "urls_attempted": len(urls),
                "hydrated": len(results),
                "health_status": health_status,
                "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
            })
        )

        return SourceResult(
            source=source_name,
            health_status=health_status,
            failure_reason=failure_reason,
            hydrated=len(results),
        )

    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        failure_reason = f"{type(exc).__name__}: {exc}"
        logger.error(
            json.dumps({
                "event": "hydrator_source_failed",
                "run_id": run_id,
                "source": source_name,
                "failure_reason": failure_reason,
                "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
            })
        )

        last_successful = _last_successful_fetch_at(resolved_db, source_name)
        _write_pipeline_run(
            resolved_db,
            run_id=run_id,
            source=source_name,
            health_status="failed",
            failure_reason=failure_reason,
            started_at=started_at,
            finished_at=finished_at,
            last_successful_fetch_at=last_successful,
        )
        _emit_transition_event_if_needed(
            resolved_db, source_name, prev_status, "failed", failure_reason, run_id
        )

        return SourceResult(
            source=source_name,
            health_status="failed",
            failure_reason=failure_reason,
        )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _write_pipeline_run(
    db_path: Path,
    *,
    run_id: str,
    source: str,
    health_status: str,
    failure_reason: Optional[str],
    started_at: datetime,
    finished_at: datetime,
    last_successful_fetch_at: Optional[datetime],
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO pipeline_runs
                (run_id, source, health_status, failure_reason,
                 started_at, finished_at, last_successful_fetch_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source,
                health_status,
                failure_reason,
                started_at.isoformat(),
                finished_at.isoformat(),
                last_successful_fetch_at.isoformat() if last_successful_fetch_at else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _get_previous_status(db_path: Path, source: str) -> str:
    """Return the most recent health_status for source, or 'never_run'."""
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


def _last_successful_fetch_at(db_path: Path, source: str) -> Optional[datetime]:
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


def _emit_transition_event_if_needed(
    db_path: Path,
    source: str,
    previous_status: str,
    new_status: str,
    failure_reason: Optional[str],
    run_id: str,
) -> None:
    """Write a source_failure event when status transitions to degraded/failed."""
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


def _get_pending_hydration_urls(db_path: Path, sender: str) -> list[str]:
    """Return canonical URLs for postings whose source matches sender and hydration_status='partial'."""
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


def _update_posting_hydration(db_path: Path, url: str, jd: object) -> None:
    """Update postings table with hydrated fields and write posting_sources row."""
    conn = sqlite3.connect(db_path)
    try:
        # Look up posting_id via seen_urls
        row = conn.execute(
            "SELECT posting_id FROM seen_urls WHERE url = ? LIMIT 1",
            (url,),
        ).fetchone()
        if not row:
            logger.warning(
                json.dumps({"event": "hydration_no_posting", "url": url})
            )
            return

        posting_id = row[0]
        now = datetime.now(timezone.utc).isoformat()

        title = getattr(jd, "title", None)
        company = getattr(jd, "company", None)
        location = getattr(jd, "location", None)
        description = getattr(jd, "description", None)
        hydration_status = getattr(jd, "hydration_status", "failed")
        raw_html = getattr(jd, "raw_html", b"")
        failure_reason = getattr(jd, "failure_reason", None)
        job_id = getattr(jd, "job_id", "")

        conn.execute(
            """
            UPDATE postings SET
                canonical_title    = COALESCE(?, canonical_title),
                canonical_company  = COALESCE(?, canonical_company),
                canonical_location = COALESCE(?, canonical_location),
                full_jd            = COALESCE(?, full_jd),
                hydration_status   = ?,
                last_seen          = ?
            WHERE id = ?
            """,
            (title, company, location, description, hydration_status, now, posting_id),
        )

        # Determine source label from URL
        if "linkedin" in url:
            source_label = "linkedin_hydrator"
        else:
            source_label = "indeed_hydrator"

        raw_html_str = raw_html.decode("latin-1") if raw_html else None
        conn.execute(
            """
            INSERT OR IGNORE INTO posting_sources
                (posting_id, user_id, source, source_url, source_first_seen, raw_html)
            VALUES (?, 'default', ?, ?, ?, ?)
            """,
            (posting_id, source_label, url, now, raw_html_str),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Structured JSON log setup
# ---------------------------------------------------------------------------


def _setup_run_logger(run_id: str) -> Path:
    """Configure a per-run JSONL file handler on the root pipeline logger.

    Returns the path to the log file.
    """
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOGS_DIR / f"pipeline-{run_id}.jsonl"

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    class _PassthroughFormatter(logging.Formatter):
        """Emit the log message as-is (already JSON-encoded by callers)."""

        def format(self, record: logging.LogRecord) -> str:
            # record.getMessage() gives the rendered message string
            return record.getMessage()

    file_handler.setFormatter(_PassthroughFormatter())

    pipeline_logger = logging.getLogger(_LOGGER_NAME)
    pipeline_logger.addHandler(file_handler)
    pipeline_logger.setLevel(logging.DEBUG)

    return log_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    db_path = Path(os.environ.get("DB_PATH", Path.home() / ".jd-matcher" / "jd-matcher.db"))
    summary = run_pipeline(db_path=db_path)

    print(f"\nPipeline run complete — run_id={summary.run_id}")
    print(f"Duration: {(summary.finished_at - summary.started_at).total_seconds():.1f}s")
    print(f"Total new postings: {summary.total_new_postings}")
    print("\nPer-source results:")
    for s in summary.sources:
        status_icon = "OK" if s.health_status == "healthy" else "FAIL"
        print(f"  [{status_icon}] {s.source:<25} {s.health_status}")
        if s.failure_reason:
            print(f"        reason: {s.failure_reason}")
