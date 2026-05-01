"""Phase: embed — Embedding generation (C20).

Public API: run(**kwargs) -> dict
Returns a dict with counts consumed by the orchestrator to populate
PipelineRunSummary and the pipeline_runs row for 'embedding'.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from jd_matcher.llm.embed import embed_postings_batch

logger = logging.getLogger(__name__)


def run(
    *,
    run_id: str,
    resolved_db: Path,
    started_at: datetime,
    logger: logging.Logger,
    write_pipeline_run: Callable,
    get_pending_ids: Callable[[Path], list[int]],
    get_max_ledger_id: Callable[[Path], int],
    ledger_delta: Callable,
) -> dict:
    """Run the embedding phase.

    Embeds all postings that have a role_summary or full_jd but no embedding row.
    Returns a dict: {embeddings_written, embedding_cache_hits, embedding_skipped, ...}
    """
    embeddings_written = 0
    embedding_cache_hits = 0
    embedding_skipped = 0
    embed_posting_count = 0
    embed_batch_call_count = 0
    embed_total_cost_usd = 0.0
    health_status = "healthy"
    failure_reason: Optional[str] = None

    try:
        posting_ids = get_pending_ids(resolved_db)
        embed_posting_count = len(posting_ids)

        if posting_ids:
            max_ledger_id_before = get_max_ledger_id(resolved_db)
            embedded = embed_postings_batch(posting_ids, db_path=resolved_db)
            embeddings_written = len(embedded)

            delta = ledger_delta(resolved_db, "embedding", max_ledger_id_before)
            embedding_cache_hits = delta["cache_hits"]
            embed_total_cost_usd = delta["cost_usd"]
            # api calls = total ledger rows minus cache hits
            embed_batch_call_count = delta["count"] - embedding_cache_hits
            embedding_skipped = len(posting_ids) - len(embedded)

            logger.info(
                json.dumps({
                    "event": "embedding_phase_complete",
                    "run_id": run_id,
                    "posted_ids_count": len(posting_ids),
                    "embeddings_written": embeddings_written,
                    "skipped": embedding_skipped,
                    "cache_hits": embedding_cache_hits,
                })
            )
        else:
            logger.info(
                json.dumps({
                    "event": "embedding_phase_complete",
                    "run_id": run_id,
                    "posted_ids_count": 0,
                    "note": "no postings pending embedding",
                })
            )
    except Exception as exc:
        health_status = "failed"
        failure_reason = f"{type(exc).__name__}: {exc}"
        logger.error(
            json.dumps({
                "event": "embedding_phase_failed",
                "run_id": run_id,
                "error": failure_reason,
            })
        )

    write_pipeline_run(
        resolved_db,
        run_id=run_id,
        source="embedding",
        health_status=health_status,
        failure_reason=failure_reason,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        last_successful_fetch_at=datetime.now(timezone.utc) if health_status == "healthy" else None,
        counts={
            "posting_count": embed_posting_count,
            "batch_call_count": embed_batch_call_count,
            "cache_hit_count": embedding_cache_hits,
            "total_cost_usd": embed_total_cost_usd,
        },
    )

    return {
        "embeddings_written": embeddings_written,
        "embedding_cache_hits": embedding_cache_hits,
        "embedding_skipped": embedding_skipped,
        "health_status": health_status,
    }
