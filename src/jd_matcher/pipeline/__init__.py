"""
Pipeline orchestrator (C11) — sequences per-source ingestion, parsing, dedup, and hydration.

Sources (PoC — LinkedIn only):
  gmail_linkedin   — Gmail fetch + LinkedIn email parse + URL dedup
  hydrator_linkedin — LinkedIn JD hydration for deduped postings

Per-source isolation invariant: one source failing CANNOT cascade to others.
Mandatory persistence invariant: regardless of outcome, exactly one pipeline_runs
row is written per source per run with non-null health_status.

M3 TASK-M3-000: pipeline.py decomposed into per-phase modules under phases/.
M3 TASK-M3-000b: orchestrator slimmed to <300 lines; source-runners moved to
  phases/fetch.py + phases/hydrate.py; DB helpers moved to _helpers.py.
Public API (run_pipeline, PipelineRunSummary, SourceResult, _GMAIL_SOURCES) is
re-exported here so all existing imports remain valid.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from jd_matcher.db.init_db import init_db
from jd_matcher.filter.title_filter import filter_title  # noqa: F401 — re-exported for test patching
from jd_matcher.hydrate.indeed import hydrate as indeed_hydrate  # noqa: F401
from jd_matcher.hydrate.linkedin import hydrate as linkedin_hydrate  # noqa: F401
from jd_matcher.ingest.gmail import GmailIngester  # noqa: F401
from jd_matcher.llm.providers.config import load_llm_config
from jd_matcher.parse.indeed_email import parse as parse_indeed  # noqa: F401
from jd_matcher.parse.linkedin_email import ParsedPosting, parse as parse_linkedin  # noqa: F401
from jd_matcher.pipeline._helpers import (
    fetch_posting_row,
    get_already_linked_posting_ids,
    get_embedded_posting_ids,
    get_max_ledger_id,
    get_monthly_llm_cost,
    get_pending_embedding_ids,
    get_pending_extraction_ids,
    get_pending_hydration_urls,
    ledger_delta,
    setup_run_logger,
    write_pipeline_run,
)
from jd_matcher.pipeline.phases.dedup import run as _dedup_run
from jd_matcher.pipeline.phases.embed import run as _embed_run
from jd_matcher.pipeline.phases.extract import run as _extract_run
from jd_matcher.pipeline.phases.fetch import run_gmail_source
from jd_matcher.pipeline.phases.hardfilter import run as _hardfilter_run
from jd_matcher.pipeline.phases.hydrate import run_hydrator_source
from jd_matcher.pipeline.phases.rank import run as _rank_run

# Legacy names re-exported for test patching compat (tests patch these on this module)
_run_gmail_source = run_gmail_source
_run_hydrator_source = run_hydrator_source

_LOGGER_NAME = "jd_matcher.pipeline"
logger = logging.getLogger(_LOGGER_NAME)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"
# parents[3] = projects/jd-matcher/ (project root, one above src/)
_LOGS_DIR = Path(__file__).parents[3] / "logs"

# M1 sources in execution order.
# PoC: LinkedIn only. Indeed deferred to MVP-M1 per ALIGNMENT-LOG 2026-04-28
_GMAIL_SOURCES = ("linkedin",)
_HYDRATOR_SOURCES = ("linkedin",)


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
    """Run the full pipeline for all configured sources."""
    resolved_db = db_path or _DEFAULT_DB_PATH
    init_db(resolved_db)

    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)
    log_path = setup_run_logger(run_id, logs_dir=_LOGS_DIR)
    logger.info(json.dumps({"event": "pipeline_start", "run_id": run_id,
                            "started_at": started_at.isoformat()}))

    source_results: list[SourceResult] = []
    steps_emitted: list[str] = []

    # Phase: fetch + parse (gmail sources)
    for i, sender in enumerate(_GMAIL_SOURCES):
        source_name = f"gmail_{sender}"
        step_label = f"Fetching Gmail ({sender})… ({i + 1}/4)"
        steps_emitted.append(step_label)
        result = _run_gmail_source(source_name=source_name, sender=sender, run_id=run_id,
                                   resolved_db=resolved_db, credentials=credentials,
                                   since_days=since_days, filter_fn=filter_title,
                                   ingester_cls=GmailIngester,
                                   parser_linkedin=parse_linkedin,
                                   parser_indeed=parse_indeed)
        source_results.append(result)
        logger.info(json.dumps({"event": "source_complete", "run_id": run_id,
                                "source": source_name, "health_status": result.health_status,
                                "new_postings": result.new_postings, "step": step_label}))

    all_postings: list[ParsedPosting] = [p for r in source_results for p in r.postings]

    # Phase: hydrate
    # Wrapped in BaseException handler so that an interrupt mid-hydration
    # (which _run_hydrator_source re-raises after flushing its own row) is
    # caught here and allows downstream phases to still write their rows before
    # the signal is propagated.  KeyboardInterrupt/SystemExit are deferred to
    # after all pipeline_runs rows are persisted.
    _deferred_interrupt: Optional[BaseException] = None
    for i, sender in enumerate(_HYDRATOR_SOURCES):
        source_name = f"hydrator_{sender}"
        step_label = f"Hydrating JDs ({sender})… ({i + 3}/4)"
        steps_emitted.append(step_label)
        try:
            result = _run_hydrator_source(source_name=source_name, sender=sender, run_id=run_id,
                                          resolved_db=resolved_db,
                                          urls=get_pending_hydration_urls(resolved_db, sender),
                                          all_postings=all_postings,
                                          hydrate_linkedin_fn=linkedin_hydrate,
                                          hydrate_indeed_fn=indeed_hydrate)
            source_results.append(result)
            logger.info(json.dumps({"event": "source_complete", "run_id": run_id,
                                    "source": source_name, "health_status": result.health_status,
                                    "hydrated": result.hydrated, "step": step_label}))
        except (KeyboardInterrupt, SystemExit) as exc:
            # _run_hydrator_source already wrote the partial pipeline_runs row.
            # Defer the signal so downstream phases can still persist their rows.
            logger.warning(json.dumps({
                "event": "hydrator_signal_deferred", "run_id": run_id,
                "source": source_name,
                "signal": type(exc).__name__,
                "note": "downstream phases will write their pipeline_runs rows before signal propagates",
            }))
            _deferred_interrupt = exc
            source_results.append(SourceResult(
                source=source_name, health_status="failed",
                failure_reason=f"interrupted:{type(exc).__name__}",
            ))
            break
        except Exception as exc:
            failure_reason = f"{type(exc).__name__}: {exc}"
            logger.error(json.dumps({
                "event": "hydrator_source_exception", "run_id": run_id,
                "source": source_name, "failure_reason": failure_reason,
            }))
            write_pipeline_run(
                resolved_db, run_id=run_id, source=source_name,
                health_status="failed", failure_reason=failure_reason,
                started_at=started_at, finished_at=datetime.now(timezone.utc),
                last_successful_fetch_at=None,
            )
            source_results.append(SourceResult(
                source=source_name, health_status="failed", failure_reason=failure_reason,
            ))

    # Phase: extract (C18)
    # Per-phase isolation: catch BaseException so KeyboardInterrupt/SystemExit cannot
    # silently skip downstream phases. Each phase writes its own pipeline_runs row
    # regardless of outcome (mandatory-persistence invariant C11).
    steps_emitted.append("LLM extraction (C18)…")
    extract_result: dict = {}
    try:
        extract_result = _extract_run(
            run_id=run_id, resolved_db=resolved_db, started_at=started_at, logger=logger,
            write_pipeline_run=write_pipeline_run, get_pending_ids=get_pending_extraction_ids,
            fetch_posting=fetch_posting_row, get_max_ledger_id=get_max_ledger_id,
            ledger_delta=ledger_delta,
        )
    except BaseException as exc:
        failure_reason = f"{type(exc).__name__}: {exc}"
        logger.error(json.dumps({
            "event": "phase_aborted", "run_id": run_id, "phase": "llm_extraction",
            "failure_reason": failure_reason,
        }))
        write_pipeline_run(
            resolved_db, run_id=run_id, source="llm_extraction",
            health_status="failed", failure_reason=failure_reason,
            started_at=started_at, finished_at=datetime.now(timezone.utc),
            last_successful_fetch_at=None,
        )
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise

    # Phase: embed (C20)
    steps_emitted.append("Embedding postings (C20)…")
    embed_result: dict = {}
    try:
        embed_result = _embed_run(
            run_id=run_id, resolved_db=resolved_db, started_at=started_at, logger=logger,
            write_pipeline_run=write_pipeline_run, get_pending_ids=get_pending_embedding_ids,
            get_max_ledger_id=get_max_ledger_id, ledger_delta=ledger_delta,
        )
    except BaseException as exc:
        failure_reason = f"{type(exc).__name__}: {exc}"
        logger.error(json.dumps({
            "event": "phase_aborted", "run_id": run_id, "phase": "embedding",
            "failure_reason": failure_reason,
        }))
        write_pipeline_run(
            resolved_db, run_id=run_id, source="embedding",
            health_status="failed", failure_reason=failure_reason,
            started_at=started_at, finished_at=datetime.now(timezone.utc),
            last_successful_fetch_at=None,
        )
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise

    # Phase: dedup + merge (C21/C29/C30)
    steps_emitted.append("Dedup decisions (C21)…")
    steps_emitted.append("Merge apply (C29+C30)…")
    dedup_merge_result: dict = {}
    try:
        dedup_merge_result = _dedup_run(
            run_id=run_id, resolved_db=resolved_db, started_at=started_at, logger=logger,
            write_pipeline_run=write_pipeline_run, get_embedded_ids=get_embedded_posting_ids,
            get_already_linked=get_already_linked_posting_ids,
        )
    except BaseException as exc:
        failure_reason = f"{type(exc).__name__}: {exc}"
        logger.error(json.dumps({
            "event": "phase_aborted", "run_id": run_id, "phase": "dedup_c21",
            "failure_reason": failure_reason,
        }))
        write_pipeline_run(
            resolved_db, run_id=run_id, source="dedup_c21",
            health_status="failed", failure_reason=failure_reason,
            started_at=started_at, finished_at=datetime.now(timezone.utc),
            last_successful_fetch_at=None,
        )
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise

    # Phase: hardfilter (C33) — stub until TASK-M3-006
    try:
        _hardfilter_run(run_id=run_id, resolved_db=resolved_db, started_at=started_at,
                        logger=logger, write_pipeline_run=write_pipeline_run)
    except BaseException as exc:
        failure_reason = f"{type(exc).__name__}: {exc}"
        logger.error(json.dumps({
            "event": "phase_aborted", "run_id": run_id, "phase": "hardfilter",
            "failure_reason": failure_reason,
        }))
        write_pipeline_run(
            resolved_db, run_id=run_id, source="hardfilter",
            health_status="failed", failure_reason=failure_reason,
            started_at=started_at, finished_at=datetime.now(timezone.utc),
            last_successful_fetch_at=None,
        )
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise

    # Phase: rank (C34) — stub until TASK-M3-007
    try:
        _rank_run(run_id=run_id, resolved_db=resolved_db, started_at=started_at,
                  logger=logger, write_pipeline_run=write_pipeline_run)
    except BaseException as exc:
        failure_reason = f"{type(exc).__name__}: {exc}"
        logger.error(json.dumps({
            "event": "phase_aborted", "run_id": run_id, "phase": "rank",
            "failure_reason": failure_reason,
        }))
        write_pipeline_run(
            resolved_db, run_id=run_id, source="rank",
            health_status="failed", failure_reason=failure_reason,
            started_at=started_at, finished_at=datetime.now(timezone.utc),
            last_successful_fetch_at=None,
        )
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise

    _check_llm_cost(resolved_db, run_id)

    finished_at = datetime.now(timezone.utc)
    total_new = sum(r.new_postings for r in source_results)
    summary = PipelineRunSummary(
        run_id=run_id, started_at=started_at, finished_at=finished_at,
        sources=source_results, steps=steps_emitted, total_new_postings=total_new,
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
    logger.info(json.dumps({"event": "pipeline_complete", "run_id": run_id,
                            "finished_at": finished_at.isoformat(),
                            "total_new_postings": total_new,
                            "failed_sources": summary.failed_sources,
                            "log_path": str(log_path)}))

    if _deferred_interrupt is not None:
        raise _deferred_interrupt  # noqa: RSE102 — intentional deferred re-raise

    return summary


def _check_llm_cost(resolved_db: Path, run_id: str) -> None:
    """Emit cost-watchdog log line; swallows all errors to avoid blocking the pipeline."""
    try:
        llm_cfg = load_llm_config()
        monthly_threshold = llm_cfg.monthly_cost_warn_usd
        monthly_cost = get_monthly_llm_cost(resolved_db)
        if monthly_cost > monthly_threshold:
            logger.warning(json.dumps({
                "event": "cost_watchdog_triggered", "run_id": run_id,
                "monthly_cost_usd": monthly_cost, "threshold_usd": monthly_threshold,
                "message": (f"Monthly LLM cost ${monthly_cost:.4f} exceeds "
                            f"${monthly_threshold:.2f} threshold — review llm.yaml"),
            }))
        else:
            logger.info(json.dumps({
                "event": "cost_watchdog_ok", "run_id": run_id,
                "monthly_cost_usd": monthly_cost, "threshold_usd": monthly_threshold,
            }))
    except Exception as exc:
        logger.warning(json.dumps({
            "event": "cost_watchdog_failed", "run_id": run_id,
            "error": f"{type(exc).__name__}: {exc}",
        }))


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
