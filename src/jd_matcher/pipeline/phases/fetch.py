"""Phase: fetch — Gmail message retrieval + email parse + URL dedup (C3/C4).

Extracted from pipeline/__init__.py _run_gmail_source() (TASK-M3-000b).

Per-source isolation invariant: one source failing CANNOT cascade to others.
Mandatory persistence invariant: exactly one pipeline_runs row is written per
source per run with non-null health_status.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from jd_matcher.db.email_ingest_log import mark_filtered, update_url_counts
from jd_matcher.dedup.url_dedup import register_new
from jd_matcher.filter.title_filter import filter_title
from jd_matcher.ingest.gmail import GmailIngester
from jd_matcher.parse.indeed_email import parse as parse_indeed
from jd_matcher.parse.linkedin_email import ParsedPosting, parse as parse_linkedin
from jd_matcher.pipeline._helpers import (
    emit_transition_event_if_needed,
    get_previous_status,
    last_successful_fetch_at,
    write_pipeline_run,
)

logger = logging.getLogger("jd_matcher.pipeline")


def run_gmail_source(
    *,
    source_name: str,
    sender: str,
    run_id: str,
    resolved_db: Path,
    credentials: object,
    since_days: int,
    filter_fn: object = None,
    ingester_cls: object = None,
    parser_linkedin: object = None,
    parser_indeed: object = None,
) -> "SourceResult":
    """Fetch Gmail + parse + dedup for one sender. ALWAYS writes pipeline_runs row.

    The optional *_fn / *_cls / parser_* arguments allow the orchestrator to
    inject the module-level references (GmailIngester, parse_linkedin, etc.) so
    that test-suite monkeypatches on ``jd_matcher.pipeline.*`` take effect here
    via the caller's reference, without requiring circular imports.

    Returns a SourceResult. Import deferred to avoid circular dependency with
    the orchestrator's dataclass definitions.
    """
    from jd_matcher.pipeline import SourceResult
    _filter_title = filter_fn if filter_fn is not None else filter_title
    _GmailIngester = ingester_cls if ingester_cls is not None else GmailIngester
    _parse_linkedin = parser_linkedin if parser_linkedin is not None else parse_linkedin
    _parse_indeed = parser_indeed if parser_indeed is not None else parse_indeed

    started_at = datetime.now(timezone.utc)
    prev_status = get_previous_status(resolved_db, source_name)

    ingester_run_id = f"{run_id}_ingest_{sender}"

    try:
        since_date = datetime.now(timezone.utc) - timedelta(days=since_days)

        ingester = _GmailIngester(credentials=credentials, db_path=resolved_db)
        emails = ingester.fetch_for_sender(
            sender,
            since_date,
            run_id=ingester_run_id,
            canonical_run_id=run_id,
        )

        new_urls: list[str] = []
        parsed_postings: list[ParsedPosting] = []
        run_filtered_total = 0
        parser = _parse_linkedin if sender == "linkedin" else _parse_indeed
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
                    decision = _filter_title(posting.title, company=posting.company)
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
        write_pipeline_run(
            resolved_db,
            run_id=run_id,
            source=source_name,
            health_status="healthy",
            failure_reason=None,
            started_at=started_at,
            finished_at=finished_at,
            last_successful_fetch_at=last_successful,
        )
        emit_transition_event_if_needed(
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

        lsf = last_successful_fetch_at(resolved_db, source_name)
        write_pipeline_run(
            resolved_db,
            run_id=run_id,
            source=source_name,
            health_status="failed",
            failure_reason=failure_reason,
            started_at=started_at,
            finished_at=finished_at,
            last_successful_fetch_at=lsf,
        )
        emit_transition_event_if_needed(
            resolved_db, source_name, prev_status, "failed", failure_reason, run_id
        )

        return SourceResult(
            source=source_name,
            health_status="failed",
            failure_reason=failure_reason,
        )


def run(state: dict) -> dict:
    """Pass-through state contract for pipeline sequencer compatibility.

    The real entry point is run_gmail_source() called directly by the orchestrator.
    This shim keeps the phases/ module contract uniform.
    """
    return state
