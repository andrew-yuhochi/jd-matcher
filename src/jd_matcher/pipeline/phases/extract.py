"""Phase: extract — LLM canonical-field extraction (C18).

Public API: run(**kwargs) -> dict
Returns a dict with counts consumed by the orchestrator to populate
PipelineRunSummary and the pipeline_runs row for 'llm_extraction'.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from jd_matcher.llm.extract import extract_canonical

logger = logging.getLogger(__name__)


def run(
    *,
    run_id: str,
    resolved_db: Path,
    started_at: datetime,
    logger: logging.Logger,
    write_pipeline_run: Callable,
    get_pending_ids: Callable[[Path], list[int]],
    fetch_posting: Callable,
    get_max_ledger_id: Callable[[Path], int],
    ledger_delta: Callable,
) -> dict:
    """Run the LLM extraction phase.

    Iterates over all postings with full_jd but no successful extraction,
    calls extract_canonical() (which now writes back to postings via
    _write_postings_extracted()), and writes a pipeline_runs row.

    Returns a dict: {success_count, failure_count, cache_hits, total_cost_usd, ...}
    """
    posting_count = 0
    success_count = 0
    failure_count = 0
    cache_hits = 0
    total_cost_usd = 0.0
    health_status = "healthy"
    failure_reason: Optional[str] = None

    try:
        pending_ids = get_pending_ids(resolved_db)
        posting_count = len(pending_ids)

        if pending_ids:
            max_ledger_id_before = get_max_ledger_id(resolved_db)

            for pid in pending_ids:
                posting = fetch_posting(resolved_db, pid)
                if posting is None:
                    continue
                try:
                    extract_canonical(posting, db_path=resolved_db)
                    success_count += 1
                except Exception as exc:
                    failure_count += 1
                    logger.warning(
                        json.dumps({
                            "event": "llm_extraction_posting_failed",
                            "run_id": run_id,
                            "posting_id": pid,
                            "error": f"{type(exc).__name__}: {exc}",
                        })
                    )

            delta = ledger_delta(resolved_db, "extraction", max_ledger_id_before)
            cache_hits = delta["cache_hits"]
            total_cost_usd = delta["cost_usd"]

            if failure_count > 0 and success_count == 0:
                health_status = "failed"
                failure_reason = f"{failure_count} extraction failures, 0 successes"
            elif failure_count > 0:
                health_status = "degraded"
                failure_reason = f"{failure_count}/{posting_count} extraction failures"

        logger.info(
            json.dumps({
                "event": "llm_extraction_phase_complete",
                "run_id": run_id,
                "posting_count": posting_count,
                "success_count": success_count,
                "failure_count": failure_count,
                "cache_hits": cache_hits,
                "total_cost_usd": total_cost_usd,
            })
        )
    except Exception as exc:
        health_status = "failed"
        failure_reason = f"{type(exc).__name__}: {exc}"
        logger.error(
            json.dumps({
                "event": "llm_extraction_phase_failed",
                "run_id": run_id,
                "error": failure_reason,
            })
        )

    write_pipeline_run(
        resolved_db,
        run_id=run_id,
        source="llm_extraction",
        health_status=health_status,
        failure_reason=failure_reason,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        last_successful_fetch_at=datetime.now(timezone.utc) if health_status == "healthy" else None,
        counts={
            "posting_count": posting_count,
            "success_count": success_count,
            "parse_failure_count": failure_count,
            "cache_hit_count": cache_hits,
            "total_cost_usd": total_cost_usd,
        },
    )

    return {
        "posting_count": posting_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "cache_hits": cache_hits,
        "total_cost_usd": total_cost_usd,
        "health_status": health_status,
    }
