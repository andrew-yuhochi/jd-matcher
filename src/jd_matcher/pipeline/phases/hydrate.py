"""Phase: hydrate — JD hydration (C5).

Extracted from pipeline/__init__.py _run_hydrator_source() + _update_posting_hydration()
(TASK-M3-000b).

Per-source isolation invariant: one source failing CANNOT cascade to others.
Mandatory persistence invariant: exactly one pipeline_runs row is written per
source per run with non-null health_status.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from jd_matcher.db.email_ingest_log import increment_hydration
from jd_matcher.hydrate import compute_source_health
from jd_matcher.hydrate.indeed import hydrate as indeed_hydrate
from jd_matcher.hydrate.linkedin import hydrate as linkedin_hydrate
from jd_matcher.pipeline._helpers import (
    emit_transition_event_if_needed,
    get_previous_status,
    last_successful_fetch_at,
    write_pipeline_run,
)

logger = logging.getLogger("jd_matcher.pipeline")


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

        source_label = "linkedin_hydrator" if "linkedin" in url else "indeed_hydrator"
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


def run_hydrator_source(
    *,
    source_name: str,
    sender: str,
    run_id: str,
    resolved_db: Path,
    urls: list[str],
    all_postings: list | None = None,
    hydrate_linkedin_fn: object = None,
    hydrate_indeed_fn: object = None,
) -> "SourceResult":
    """Hydrate all pending JDs for one sender. ALWAYS writes pipeline_runs row.

    The optional hydrate_*_fn arguments allow the orchestrator to inject the
    module-level references so test-suite monkeypatches on
    ``jd_matcher.pipeline.linkedin_hydrate`` take effect here.
    """
    from jd_matcher.pipeline import SourceResult

    started_at = datetime.now(timezone.utc)
    prev_status = get_previous_status(resolved_db, source_name)

    url_to_gmail_id: dict[str, str] = {}
    for posting in (all_postings or []):
        if posting.url not in url_to_gmail_id:
            url_to_gmail_id[posting.url] = posting.gmail_message_id

    _linkedin_hydrate = hydrate_linkedin_fn if hydrate_linkedin_fn is not None else linkedin_hydrate
    _indeed_hydrate = hydrate_indeed_fn if hydrate_indeed_fn is not None else indeed_hydrate

    try:
        hydrate_fn = _linkedin_hydrate if sender == "linkedin" else _indeed_hydrate
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
        lsf = started_at if health_status == "healthy" else last_successful_fetch_at(resolved_db, source_name)
        write_pipeline_run(
            resolved_db,
            run_id=run_id,
            source=source_name,
            health_status=health_status,
            failure_reason=failure_reason,
            started_at=started_at,
            finished_at=finished_at,
            last_successful_fetch_at=lsf,
        )
        emit_transition_event_if_needed(
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

    The real entry point is run_hydrator_source() called directly by the orchestrator.
    """
    return state
