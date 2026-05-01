"""
Pipeline orchestrator (C11) — sequences per-source ingestion, parsing, dedup, and hydration.

Sources (PoC — LinkedIn only):
  gmail_linkedin   — Gmail fetch + LinkedIn email parse + URL dedup
  hydrator_linkedin — LinkedIn JD hydration for deduped postings

Per-source isolation invariant: one source failing CANNOT cascade to others.
Mandatory persistence invariant: regardless of outcome, exactly one pipeline_runs
row is written per source per run with non-null health_status.

M3 TASK-M3-000: pipeline.py decomposed into per-phase modules under phases/.
Public API (run_pipeline, PipelineRunSummary, SourceResult, _GMAIL_SOURCES) is
re-exported here so all existing imports remain valid.
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

from jd_matcher.db.email_ingest_log import increment_hydration, mark_filtered, update_url_counts
from jd_matcher.filter.title_filter import filter_title
from jd_matcher.db.init_db import init_db
from jd_matcher.dedup.engine import DedupDecision, decide as dedup_decide
from jd_matcher.dedup.merge import MergeResult, apply_decision as dedup_apply
from jd_matcher.dedup.repost import detect_repost
from jd_matcher.dedup.url_dedup import register_new
from jd_matcher.hydrate import compute_source_health
from jd_matcher.hydrate.indeed import hydrate as indeed_hydrate
from jd_matcher.hydrate.linkedin import hydrate as linkedin_hydrate
from jd_matcher.ingest.gmail import GmailIngester
from jd_matcher.llm.embed import embed_postings_batch
from jd_matcher.llm.extract import PostingRow, extract_canonical
from jd_matcher.llm.providers.config import load_llm_config
from jd_matcher.parse.indeed_email import parse as parse_indeed
from jd_matcher.parse.linkedin_email import ParsedPosting, parse as parse_linkedin

_LOGGER_NAME = "jd_matcher.pipeline"
logger = logging.getLogger(_LOGGER_NAME)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"
# parents[2] = projects/jd-matcher/ (one above src/)
_LOGS_DIR = Path(__file__).parents[3] / "logs"

# M1 sources in execution order
# PoC: LinkedIn only. Indeed deferred to MVP-M1 per ALIGNMENT-LOG 2026-04-28
_GMAIL_SOURCES = ("linkedin",)
_HYDRATOR_SOURCES = ("linkedin",)

_STEP_LABELS = [
    "Fetching Gmail (linkedin)… (1/2)",
    "Hydrating JDs (linkedin)… (2/2)",
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
    filtered_count: int = 0
    postings: list[ParsedPosting] = field(default_factory=list)


@dataclass
class PipelineRunSummary:
    run_id: str
    started_at: datetime
    finished_at: datetime
    sources: list[SourceResult]
    steps: list[str]
    total_new_postings: int
    embeddings_written: int = 0
    embedding_cache_hits: int = 0
    embedding_skipped: int = 0
    dedup_decisions_total: int = 0
    dedup_action_new: int = 0
    dedup_action_merge: int = 0
    dedup_full_jd_skipped: int = 0
    dedup_block_zero: int = 0
    merges_applied: int = 0
    new_canonicals_created: int = 0
    reposts_detected: int = 0

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
    """Run the full pipeline for all configured sources.

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
    # Phase: fetch + parse (gmail sources)
    # -----------------------------------------------------------------------
    from jd_matcher.pipeline.phases.fetch import run as fetch_run
    from jd_matcher.pipeline.phases.parse import run as parse_run

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

    all_postings: list[ParsedPosting] = []
    for gmail_result in source_results:
        all_postings.extend(gmail_result.postings)

    li_urls = _get_pending_hydration_urls(resolved_db, "linkedin")
    hydration_urls = {"linkedin": li_urls}

    # -----------------------------------------------------------------------
    # Phase: hydrate
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

    # -----------------------------------------------------------------------
    # Phase: extract (C18 — LLM extraction)
    # -----------------------------------------------------------------------
    from jd_matcher.pipeline.phases.extract import run as extract_run

    step_label = "LLM extraction (C18)…"
    steps_emitted.append(step_label)
    extract_result = extract_run(
        run_id=run_id,
        resolved_db=resolved_db,
        started_at=started_at,
        logger=logger,
        write_pipeline_run=_write_pipeline_run,
        get_pending_ids=_get_pending_extraction_ids,
        fetch_posting=_fetch_posting_row,
        get_max_ledger_id=_get_max_ledger_id,
        ledger_delta=_ledger_delta,
    )

    # -----------------------------------------------------------------------
    # Phase: embed (C20 — Embedding)
    # -----------------------------------------------------------------------
    from jd_matcher.pipeline.phases.embed import run as embed_run

    step_label = "Embedding postings (C20)…"
    steps_emitted.append(step_label)
    embed_result = embed_run(
        run_id=run_id,
        resolved_db=resolved_db,
        started_at=started_at,
        logger=logger,
        write_pipeline_run=_write_pipeline_run,
        get_pending_ids=_get_pending_embedding_ids,
        get_max_ledger_id=_get_max_ledger_id,
        ledger_delta=_ledger_delta,
    )

    # -----------------------------------------------------------------------
    # Phase: dedup + merge (C21 + C30 + C29 — interleaved per-posting)
    # -----------------------------------------------------------------------
    from jd_matcher.pipeline.phases.dedup import run as dedup_run
    from jd_matcher.pipeline.phases.merge import run as merge_run

    step_label = "Dedup decisions (C21)…"
    steps_emitted.append(step_label)
    step_label = "Merge apply (C29+C30)…"
    steps_emitted.append(step_label)
    dedup_merge_result = dedup_run(
        run_id=run_id,
        resolved_db=resolved_db,
        started_at=started_at,
        logger=logger,
        write_pipeline_run=_write_pipeline_run,
        get_embedded_ids=_get_embedded_posting_ids,
        get_already_linked=_get_already_linked_posting_ids,
    )

    # -----------------------------------------------------------------------
    # Phase: hardfilter (C33) — stub until TASK-M3-006
    # -----------------------------------------------------------------------
    from jd_matcher.pipeline.phases.hardfilter import run as hardfilter_run

    hardfilter_run(
        run_id=run_id,
        resolved_db=resolved_db,
        started_at=started_at,
        logger=logger,
        write_pipeline_run=_write_pipeline_run,
    )

    # -----------------------------------------------------------------------
    # Phase: rank (C34) — stub until TASK-M3-007
    # -----------------------------------------------------------------------
    from jd_matcher.pipeline.phases.rank import run as rank_run

    rank_run(
        run_id=run_id,
        resolved_db=resolved_db,
        started_at=started_at,
        logger=logger,
        write_pipeline_run=_write_pipeline_run,
    )

    # -----------------------------------------------------------------------
    # Cost-watchdog: emit WARNING if monthly LLM spend exceeds threshold.
    # -----------------------------------------------------------------------
    try:
        llm_cfg = load_llm_config()
        monthly_threshold = llm_cfg.monthly_cost_warn_usd
        monthly_cost = _get_monthly_llm_cost(resolved_db)
        if monthly_cost > monthly_threshold:
            logger.warning(
                json.dumps({
                    "event": "cost_watchdog_triggered",
                    "run_id": run_id,
                    "monthly_cost_usd": monthly_cost,
                    "threshold_usd": monthly_threshold,
                    "message": (
                        f"Monthly LLM cost ${monthly_cost:.4f} exceeds "
                        f"${monthly_threshold:.2f} threshold — review llm.yaml"
                    ),
                })
            )
        else:
            logger.info(
                json.dumps({
                    "event": "cost_watchdog_ok",
                    "run_id": run_id,
                    "monthly_cost_usd": monthly_cost,
                    "threshold_usd": monthly_threshold,
                })
            )
    except Exception as exc:
        logger.warning(
            json.dumps({
                "event": "cost_watchdog_failed",
                "run_id": run_id,
                "error": f"{type(exc).__name__}: {exc}",
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
        embeddings_written=embed_result.get("embeddings_written", 0),
        embedding_cache_hits=embed_result.get("embedding_cache_hits", 0),
        embedding_skipped=embed_result.get("embedding_skipped", 0),
        dedup_decisions_total=dedup_merge_result.get("dedup_total", 0),
        dedup_action_new=dedup_merge_result.get("dedup_new", 0),
        dedup_action_merge=dedup_merge_result.get("dedup_merge", 0),
        dedup_full_jd_skipped=dedup_merge_result.get("dedup_full_jd_skipped", 0),
        dedup_block_zero=dedup_merge_result.get("dedup_block_zero", 0),
        merges_applied=dedup_merge_result.get("merges_applied", 0),
        new_canonicals_created=dedup_merge_result.get("new_canonicals_created", 0),
        reposts_detected=dedup_merge_result.get("reposts_detected", 0),
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
    """Fetch Gmail + parse + dedup for one sender. ALWAYS writes pipeline_runs row."""
    started_at = datetime.now(timezone.utc)
    prev_status = _get_previous_status(resolved_db, source_name)

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
        run_filtered_total = 0
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
                urls_filtered = 0
                drop_reasons: list[str] = []

                for posting in postings:
                    decision = filter_title(posting.title, company=posting.company)
                    if decision.action == "drop":
                        urls_filtered += 1
                        run_filtered_total += 1
                        if decision.matched_pattern:
                            drop_reasons.append(decision.matched_pattern)
                        continue

                    outcome, _ = register_new(posting, conn=conn, db_path=resolved_db)
                    if outcome == "new":
                        new_urls.append(posting.url)
                        urls_new += 1
                        urls_created += 1

                if urls_extracted > 0 and urls_filtered == urls_extracted:
                    try:
                        mark_filtered(
                            gmail_message_id=raw_email.id,
                            filter_reason=", ".join(drop_reasons) if drop_reasons else None,
                            db_path=resolved_db,
                            conn=conn,
                        )
                    except Exception:
                        logger.warning(
                            "C19 mark_filtered failed for gmail_message_id=%s",
                            raw_email.id,
                            exc_info=True,
                        )

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
                "filtered_by_title": run_filtered_total,
                "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
            })
        )

        return SourceResult(
            source=source_name,
            health_status="healthy",
            new_postings=len(new_urls),
            filtered_count=run_filtered_total,
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
    """Hydrate all pending JDs for one sender. ALWAYS writes pipeline_runs row."""
    started_at = datetime.now(timezone.utc)
    prev_status = _get_previous_status(resolved_db, source_name)

    url_to_gmail_id: dict[str, str] = {}
    for posting in (all_postings or []):
        if posting.url not in url_to_gmail_id:
            url_to_gmail_id[posting.url] = posting.gmail_message_id

    try:
        hydrate_fn = linkedin_hydrate if sender == "linkedin" else indeed_hydrate
        results = []
        exception_count = 0
        last_exception_reason: Optional[str] = None
        for url in urls:
            try:
                jd = hydrate_fn(url)
                results.append(jd)
                _update_posting_hydration(resolved_db, url, jd)
            except sqlite3.OperationalError as exc:
                logger.warning(
                    "DB lock on url=%s — skipping, will retry next sync: %s", url, exc
                )
                exception_count += 1
                last_exception_reason = f"db_lock:{exc}"
                continue
            except Exception as exc:
                logger.error(
                    "Hydration failed for url=%s: %s", url, exc, exc_info=True
                )
                exception_count += 1
                last_exception_reason = f"{type(exc).__name__}:{exc}"
                continue

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

        if urls and not results and exception_count == len(urls):
            health_status = "failed"
            failure_reason = last_exception_reason or "all_urls_raised_exception"

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
# DB helpers — shared across orchestrator and phase modules
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


def _get_previous_status(db_path: Path, source: str) -> str:
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
    conn = sqlite3.connect(db_path)
    try:
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


def _get_pending_embedding_ids(db_path: Path) -> list[int]:
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


def _get_max_ledger_id(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM llm_call_ledger"
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def _get_embedded_posting_ids(db_path: Path) -> list[int]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT CAST(posting_id AS INTEGER) FROM posting_embeddings ORDER BY posting_id"
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def _get_already_linked_posting_ids(db_path: Path) -> set[int]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT CAST(posting_id AS INTEGER) FROM posting_canonical_links"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def _ledger_delta(db_path: Path, call_kind: str, before_id: int) -> dict:
    """Return {count, cache_hits, cost_usd} for ledger rows with call_kind after before_id.

    Replaces 6 near-identical _count_*_since / _sum_*_since helpers per
    ARCHITECTURE-REVIEW-2026-04-29 §3 recommendation.
    """
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


def _get_pending_extraction_ids(db_path: Path) -> list[int]:
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


def _fetch_posting_row(db_path: Path, posting_id: int) -> "PostingRow | None":
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


def _get_monthly_llm_cost(db_path: Path) -> float:
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


# ---------------------------------------------------------------------------
# Structured JSON log setup
# ---------------------------------------------------------------------------


def _setup_run_logger(run_id: str) -> Path:
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOGS_DIR / f"pipeline-{run_id}.jsonl"

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
