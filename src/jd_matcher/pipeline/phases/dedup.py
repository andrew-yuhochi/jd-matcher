"""Phase: dedup + merge — Two-stage dedup (C21 + C30 + C29), interleaved per-posting.

Each posting's decide → detect_repost → apply runs atomically before the
next posting's decide() executes. This is critical: dedup_decide() reads
canonical_postings to find block candidates. Batching decide() across all
postings before any apply() would cause every posting to get action='new'
because canonical_postings would be empty. The per-posting interleave ensures
posting B's decide() sees the canonical that posting A's apply() just created.

Public API: run(**kwargs) -> dict
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from jd_matcher.dedup.engine import DedupDecision, decide as dedup_decide
from jd_matcher.dedup.merge import MergeResult, apply_decision as dedup_apply
from jd_matcher.dedup.repost import detect_repost

logger = logging.getLogger(__name__)


def run(
    *,
    run_id: str,
    resolved_db: Path,
    started_at: datetime,
    logger: logging.Logger,
    write_pipeline_run: Callable,
    get_embedded_ids: Callable[[Path], list[int]],
    get_already_linked: Callable[[Path], set[int]],
) -> dict:
    """Run the combined dedup-decide + repost-detect + merge-apply phase.

    Writes two pipeline_runs rows: 'dedup_c21' and 'dedup_merge_c29'.
    Returns a dict with all stats consumed by PipelineRunSummary.
    """
    dedup_total = 0
    dedup_new = 0
    dedup_merge = 0
    dedup_full_jd_skipped = 0
    dedup_block_zero = 0
    merges_applied = 0
    new_canonicals_created = 0
    reposts_detected = 0

    dedup_health_status = "healthy"
    dedup_failure_reason: Optional[str] = None
    merge_health_status = "healthy"
    merge_failure_reason: Optional[str] = None

    try:
        embedded_ids = get_embedded_ids(resolved_db)
        already_linked = get_already_linked(resolved_db)

        for pid in embedded_ids:
            if pid in already_linked:
                logger.debug(
                    json.dumps({
                        "event": "dedup_skip_already_linked",
                        "run_id": run_id,
                        "posting_id": pid,
                    })
                )
                continue

            # C21: decide
            try:
                decision: DedupDecision = dedup_decide(pid, db_path=resolved_db)
                dedup_total += 1
                if decision.action == "merge":
                    dedup_merge += 1
                elif decision.action == "pending_gatekeeper":
                    logger.warning(
                        json.dumps({
                            "event": "dedup_pending_gatekeeper",
                            "run_id": run_id,
                            "posting_id": pid,
                            "fuse_score": decision.stage2_top_match_score,
                        })
                    )
                    continue
                else:
                    dedup_new += 1

                if "extraction_failed_full_jd_fallback" in decision.blocked_by:
                    dedup_full_jd_skipped += 1
                if decision.stage1_block_size == 0:
                    dedup_block_zero += 1

                logger.info(
                    json.dumps({
                        "event": "dedup_decision",
                        "run_id": run_id,
                        "posting_id": pid,
                        "action": decision.action,
                        "merge_kind": decision.merge_kind,
                        "similarity": decision.similarity,
                        "stage1_block_size": decision.stage1_block_size,
                        "stage2_top_match_score": decision.stage2_top_match_score,
                        "target_canonical_id": decision.target_canonical_id,
                    })
                )
            except Exception as exc:
                logger.warning(
                    json.dumps({
                        "event": "dedup_decision_failed",
                        "run_id": run_id,
                        "posting_id": pid,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                )
                continue

            # C30: repost detection + C29: merge apply
            try:
                repost_decision = detect_repost(decision, pid, db_path=resolved_db)
                if repost_decision.merge_kind == "repost":
                    reposts_detected += 1

                merge_result: MergeResult = dedup_apply(repost_decision, pid, db_path=resolved_db)
                if merge_result.was_new:
                    new_canonicals_created += 1
                else:
                    merges_applied += 1

                logger.info(
                    json.dumps({
                        "event": "merge_applied",
                        "run_id": run_id,
                        "posting_id": pid,
                        "canonical_id": merge_result.canonical_id,
                        "was_new": merge_result.was_new,
                        "merge_kind": merge_result.merge_kind,
                        "fields_updated": merge_result.fields_updated,
                    })
                )
            except Exception as exc:
                logger.warning(
                    json.dumps({
                        "event": "merge_apply_failed",
                        "run_id": run_id,
                        "posting_id": pid,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                )

    except Exception as exc:
        dedup_health_status = "failed"
        merge_health_status = "failed"
        dedup_failure_reason = f"{type(exc).__name__}: {exc}"
        merge_failure_reason = dedup_failure_reason
        logger.error(
            json.dumps({
                "event": "dedup_merge_phase_failed",
                "run_id": run_id,
                "error": dedup_failure_reason,
            })
        )

    write_pipeline_run(
        resolved_db,
        run_id=run_id,
        source="dedup_c21",
        health_status=dedup_health_status,
        failure_reason=dedup_failure_reason,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        last_successful_fetch_at=datetime.now(timezone.utc) if dedup_health_status == "healthy" else None,
    )
    logger.info(
        json.dumps({
            "event": "dedup_phase_complete",
            "run_id": run_id,
            "decisions_total": dedup_total,
            "action_new": dedup_new,
            "action_merge": dedup_merge,
            "full_jd_skipped": dedup_full_jd_skipped,
            "block_zero_short_circuit": dedup_block_zero,
        })
    )

    write_pipeline_run(
        resolved_db,
        run_id=run_id,
        source="dedup_merge_c29",
        health_status=merge_health_status,
        failure_reason=merge_failure_reason,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        last_successful_fetch_at=datetime.now(timezone.utc) if merge_health_status == "healthy" else None,
    )
    logger.info(
        json.dumps({
            "event": "merge_phase_complete",
            "run_id": run_id,
            "merges_applied": merges_applied,
            "new_canonicals_created": new_canonicals_created,
            "reposts_detected": reposts_detected,
        })
    )

    return {
        "dedup_total": dedup_total,
        "dedup_new": dedup_new,
        "dedup_merge": dedup_merge,
        "dedup_full_jd_skipped": dedup_full_jd_skipped,
        "dedup_block_zero": dedup_block_zero,
        "merges_applied": merges_applied,
        "new_canonicals_created": new_canonicals_created,
        "reposts_detected": reposts_detected,
    }
