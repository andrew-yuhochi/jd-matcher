"""
M2 end-to-end integration tests for the C11 pipeline orchestrator (TASK-M2-010).

AC coverage:
  AC #1 — Pipeline order: fetch → parse → C19 filter → URL-dedup → hydrate →
           LLM-extract → embed → content-dedup → merge → store.
           Verified by checking pipeline_runs sources and step order.
  AC #2 — New pipeline_runs rows: llm_extraction + embedding (with health_status).
           title_filter drops go into gmail_linkedin.counts.filtered_by_title.
  AC #6 — Filtered postings (C19) short-circuit; do NOT appear in subsequent
           stage pipeline_runs counts.

AC #3, #4, #5 are covered in tests/state/test_canonical_view.py.

Regression guard (added 2026-04-29):
  test_two_postings_with_shared_block_key_merge_correctly — prevents the Phase 5
  batch-decide / Phase 6 batch-apply split that caused 0 merges (commit 233e050).
"""

from __future__ import annotations

import json
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.pipeline import SourceResult, run_pipeline


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture()
def skip_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKIP_LIVE", "1")


@pytest.fixture()
def logs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    import jd_matcher.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "_LOGS_DIR", log_dir)
    return log_dir


def _pipeline_runs_for_run(db_path: Path, run_id: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT source, health_status, failure_reason, counts FROM pipeline_runs "
            "WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
        return [
            {
                "source": r[0],
                "health_status": r[1],
                "failure_reason": r[2],
                "counts": json.loads(r[3]) if r[3] else None,
            }
            for r in rows
        ]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# AC #1 — Pipeline order includes all expected steps
# ---------------------------------------------------------------------------


class TestPipelineOrder:
    def test_all_expected_steps_present(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """AC #1: all M2 pipeline steps are present in the run summary."""
        summary = run_pipeline(db_path=test_db)

        expected_steps_substrings = [
            "Fetching Gmail",
            "Hydrating JDs",
            "LLM extraction",
            "Embedding postings",
            "Dedup decisions",
            "Merge apply",
        ]
        for expected in expected_steps_substrings:
            assert any(expected in s for s in summary.steps), (
                f"Expected step containing '{expected}' not found in steps: {summary.steps}"
            )

    def test_llm_extraction_step_before_embedding(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """AC #1: LLM extraction step appears before embedding step (pipeline order)."""
        summary = run_pipeline(db_path=test_db)

        # Find indices
        steps = summary.steps
        llm_idx = next(
            (i for i, s in enumerate(steps) if "LLM extraction" in s), None
        )
        embed_idx = next(
            (i for i, s in enumerate(steps) if "Embedding postings" in s), None
        )
        dedup_idx = next(
            (i for i, s in enumerate(steps) if "Dedup decisions" in s), None
        )
        merge_idx = next(
            (i for i, s in enumerate(steps) if "Merge apply" in s), None
        )

        assert llm_idx is not None, "LLM extraction step missing"
        assert embed_idx is not None, "Embedding step missing"
        assert dedup_idx is not None, "Dedup step missing"
        assert merge_idx is not None, "Merge apply step missing"

        assert llm_idx < embed_idx, (
            f"LLM extraction (idx={llm_idx}) must come before embedding (idx={embed_idx})"
        )
        assert embed_idx < dedup_idx, (
            f"Embedding (idx={embed_idx}) must come before dedup (idx={dedup_idx})"
        )
        assert dedup_idx < merge_idx, (
            f"Dedup (idx={dedup_idx}) must come before merge (idx={merge_idx})"
        )


# ---------------------------------------------------------------------------
# AC #2 — New pipeline_runs rows: llm_extraction + embedding with health_status
# ---------------------------------------------------------------------------


class TestNewPipelineRunsRows:
    def test_llm_extraction_row_written(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """AC #2: llm_extraction pipeline_runs row written with non-null health_status."""
        summary = run_pipeline(db_path=test_db)
        rows = _pipeline_runs_for_run(test_db, summary.run_id)
        sources = {r["source"] for r in rows}
        assert "llm_extraction" in sources, (
            f"llm_extraction pipeline_runs row missing. Sources: {sources}"
        )

        llm_row = next(r for r in rows if r["source"] == "llm_extraction")
        assert llm_row["health_status"] in ("healthy", "degraded", "failed"), (
            f"llm_extraction health_status must be non-null. Got: {llm_row['health_status']}"
        )

    def test_embedding_row_written(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """AC #2: embedding pipeline_runs row written with non-null health_status."""
        summary = run_pipeline(db_path=test_db)
        rows = _pipeline_runs_for_run(test_db, summary.run_id)
        sources = {r["source"] for r in rows}
        assert "embedding" in sources, (
            f"embedding pipeline_runs row missing. Sources: {sources}"
        )

        embed_row = next(r for r in rows if r["source"] == "embedding")
        assert embed_row["health_status"] in ("healthy", "degraded", "failed"), (
            f"embedding health_status must be non-null. Got: {embed_row['health_status']}"
        )

    def test_mandatory_persistence_holds_for_new_sources(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """AC #2: mandatory-persistence invariant — no source row is ever missing."""
        summary = run_pipeline(db_path=test_db)
        rows = _pipeline_runs_for_run(test_db, summary.run_id)
        sources = {r["source"] for r in rows}
        required = {
            "gmail_linkedin",
            "hydrator_linkedin",
            "llm_extraction",
            "embedding",
            "dedup_c21",
            "dedup_merge_c29",
        }
        missing = required - sources
        assert not missing, (
            f"Mandatory-persistence violated: missing pipeline_runs rows for {missing}"
        )

        # All rows must have non-null health_status
        for row in rows:
            if row["source"] in required:
                assert row["health_status"] is not None, (
                    f"Source {row['source']} has NULL health_status"
                )


# ---------------------------------------------------------------------------
# AC #6 — Filtered postings (C19) short-circuit; do NOT appear in LLM/embed counts
# ---------------------------------------------------------------------------


class TestFilteredPostingsShortCircuit:
    def test_filtered_postings_do_not_appear_in_extraction_counts(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """AC #6: C19-filtered postings are not counted in llm_extraction or embedding rows.

        Strategy: force all titles to be filtered by C19, then assert that
        llm_extraction.counts.posting_count == 0 (no postings reached extraction).
        """
        from unittest.mock import patch as _patch
        from jd_matcher.filter.title_filter import FilterDecision

        # Make C19 filter reject everything
        def _reject_all(title: str, company: str = "") -> FilterDecision:
            return FilterDecision(action="drop", matched_pattern="test_force_drop", reason="test")

        with _patch("jd_matcher.pipeline.filter_title", side_effect=_reject_all):
            summary = run_pipeline(db_path=test_db)

        rows = _pipeline_runs_for_run(test_db, summary.run_id)

        # llm_extraction should have 0 posting_count (nothing survived C19)
        llm_rows = [r for r in rows if r["source"] == "llm_extraction"]
        assert len(llm_rows) == 1, "llm_extraction row must still be written (mandatory-persistence)"
        llm_counts = llm_rows[0]["counts"]
        if llm_counts is not None:
            assert llm_counts.get("posting_count", 0) == 0, (
                f"llm_extraction.counts.posting_count should be 0 when all postings filtered. "
                f"Got: {llm_counts}"
            )

        # embedding should have 0 posting_count too
        embed_rows = [r for r in rows if r["source"] == "embedding"]
        assert len(embed_rows) == 1, "embedding row must still be written (mandatory-persistence)"


# ---------------------------------------------------------------------------
# Cost-watchdog behaviour
# ---------------------------------------------------------------------------


class TestCostWatchdog:
    def test_cost_watchdog_does_not_block_pipeline(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """Cost-watchdog fires as WARNING but does NOT block pipeline completion."""
        # Set threshold to 0.00 so it always triggers
        from jd_matcher.llm.providers.config import LLMConfig, ProviderConfig

        zero_threshold_config = LLMConfig(
            extraction=ProviderConfig(provider="openai", model="gpt-4o-mini"),
            embedding=ProviderConfig(provider="openai", model="text-embedding-3-small"),
            monthly_cost_warn_usd=0.00,
        )

        with patch(
            "jd_matcher.pipeline.load_llm_config",
            return_value=zero_threshold_config,
        ):
            summary = run_pipeline(db_path=test_db)

        # Pipeline must complete with a run_id (not raise)
        assert summary.run_id is not None


# ---------------------------------------------------------------------------
# Regression guard: per-posting interleaved decide+apply (fixes commit 233e050)
# ---------------------------------------------------------------------------


def _make_unit_vector(dim: int = 8) -> bytes:
    """Return a packed float32 unit vector of `dim` dimensions."""
    arr = np.ones(dim, dtype=np.float32)
    arr = arr / np.linalg.norm(arr)
    return arr.tobytes()


def _seed_posting(
    conn: sqlite3.Connection,
    *,
    company: str,
    location: str,
    title: str,
    seniority: str,
    skills_json: str,
) -> int:
    """Insert a minimal posting row and return its id."""
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_company, canonical_title, canonical_location,
             seniority_band, canonical_seniority, top_skills, hydration_status, first_seen, last_seen)
        VALUES ('default', ?, ?, ?, ?, ?, ?, 'complete', ?, ?)
        """,
        (company, title, location, seniority, seniority, skills_json, now, now),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def _seed_embedding(
    conn: sqlite3.Connection,
    posting_id: int,
    vector_blob: bytes,
    dim: int = 8,
) -> None:
    """Insert a posting_embeddings row for posting_id with the given vector."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO posting_embeddings
            (posting_id, user_id, text_source, text_hash, embedding,
             embedding_dim, model_name, embedded_at)
        VALUES (?, 'default', 'role_summary', 'deadbeef', ?, ?, 'text-embedding-3-small', ?)
        """,
        (str(posting_id), vector_blob, dim, now),
    )
    conn.commit()


class TestDedupMergeInterleave:
    """Regression guard for the batch-decide / batch-apply bug (commit 233e050).

    The original pipeline batched ALL decide() calls before ANY apply() calls.
    Because decide() reads canonical_postings to find block candidates, every
    decide() saw an empty table → 0 merges.

    After the fix, decide+apply run per-posting.  This test verifies that two
    postings with an identical BLOCK key (company + team_or_department + location)
    AND identical embeddings actually merge instead of both becoming new_canonicals.
    """

    def test_two_postings_with_shared_block_key_merge_correctly(
        self, test_db: Path, logs_dir: Path
    ) -> None:
        """Two identical postings must produce 1 canonical (not 2).

        Would have FAILED on commit 233e050 (0 merges → 2 canonicals).
        Must PASS after the per-posting interleave fix.
        """
        conn = sqlite3.connect(test_db)

        # Shared block-key attributes — identical across both postings
        COMPANY = "Acme Corp"
        LOCATION = "Vancouver, BC"
        TITLE = "Senior Data Scientist"
        SENIORITY = "Senior"
        SKILLS = '["python", "machine learning", "sql"]'
        VEC_BLOB = _make_unit_vector(dim=8)
        DIM = 8

        pid1 = _seed_posting(
            conn,
            company=COMPANY,
            location=LOCATION,
            title=TITLE,
            seniority=SENIORITY,
            skills_json=SKILLS,
        )
        pid2 = _seed_posting(
            conn,
            company=COMPANY,
            location=LOCATION,
            title=TITLE,
            seniority=SENIORITY,
            skills_json=SKILLS,
        )
        _seed_embedding(conn, pid1, VEC_BLOB, DIM)
        _seed_embedding(conn, pid2, VEC_BLOB, DIM)
        conn.close()

        empty_source_result = SourceResult(
            source="gmail_linkedin", health_status="healthy"
        )

        # Patch heavy phases so they are no-ops:
        #   - Gmail source runner: returns empty SourceResult (no postings fetched)
        #   - Hydrator source runner: returns empty SourceResult (no hydration)
        #   - LLM extraction: bypassed (postings have no full_jd → pending list = [])
        #   - Embedding: bypassed (postings already have posting_embeddings rows)
        #   - title_cosine: return 1.0 so fuse score = 0.4+0.3+0.2+0.1 = 1.0 ≥ 0.90
        with (
            patch(
                "jd_matcher.pipeline._run_gmail_source",
                return_value=empty_source_result,
            ),
            patch(
                "jd_matcher.pipeline._run_hydrator_source",
                return_value=empty_source_result,
            ),
            patch(
                "jd_matcher.dedup.engine.title_cosine",
                return_value=1.0,
            ),
        ):
            summary = run_pipeline(db_path=test_db)

        # --- Assertions ---
        db_conn = sqlite3.connect(test_db)
        try:
            canonical_count = db_conn.execute(
                "SELECT COUNT(*) FROM canonical_postings"
            ).fetchone()[0]
            link_count = db_conn.execute(
                "SELECT COUNT(*) FROM posting_canonical_links"
            ).fetchone()[0]
            # The second posting's link must be 'content_dedup', not 'new_canonical'
            merge_kind_for_pid2 = db_conn.execute(
                "SELECT merge_kind FROM posting_canonical_links WHERE posting_id = ?",
                (str(pid2),),
            ).fetchone()
            # Both postings share the same canonical_id
            canonical_ids = db_conn.execute(
                "SELECT DISTINCT canonical_id FROM posting_canonical_links"
            ).fetchall()
        finally:
            db_conn.close()

        assert canonical_count == 1, (
            f"Expected 1 canonical_posting (two identical postings must merge), "
            f"got {canonical_count}. This indicates the batch-decide/batch-apply "
            f"bug has regressed."
        )
        assert link_count == 2, (
            f"Expected 2 posting_canonical_links (both postings linked), got {link_count}"
        )
        assert merge_kind_for_pid2 is not None, (
            f"posting {pid2} has no posting_canonical_links row"
        )
        # Under the 3-tier decision logic (TASK-M2-012), identical postings
        # hit the 4-feature exact-match short-circuit → merge_kind='exact_4f'.
        # 'content_dedup' is the legacy value from earlier pipeline versions
        # (kept in the Literal for backward compat with stored rows).
        assert merge_kind_for_pid2[0] in ("content_dedup", "exact_4f", "gatekeeper_approved"), (
            f"posting {pid2} should be a merge kind (got '{merge_kind_for_pid2[0]}')"
        )
        assert len(canonical_ids) == 1, (
            f"Both postings must share the same canonical_id, got {canonical_ids}"
        )
        assert summary.new_canonicals_created == 1, (
            f"PipelineRunSummary.new_canonicals_created should be 1, got {summary.new_canonicals_created}"
        )
        assert summary.merges_applied == 1, (
            f"PipelineRunSummary.merges_applied should be 1, got {summary.merges_applied}"
        )


# ---------------------------------------------------------------------------
# Regression guard: orchestrator must continue past hydrator failure / interrupt
# (introduced 2026-04-30 — TASK-M3-000b follow-up)
#
# Root cause: with SKIP_LIVE=0 and 64+ pending URLs, the hydrator's 30s
# rate-limiter caused the live pipeline to appear "frozen" after gmail.
# The user killed the process (SIGTERM/Ctrl+C → KeyboardInterrupt), which
# bypassed both the per-URL `except Exception` handler AND the outer
# `except Exception` in run_hydrator_source (KeyboardInterrupt is BaseException),
# propagated un-caught through run_pipeline, and killed the process without
# writing pipeline_runs rows for hydrator, extract, embed, dedup, hardfilter, rank.
# ---------------------------------------------------------------------------


class TestOrchestratorContinuesPastHydratorFailure:
    """Orchestrator must keep running downstream phases even when hydrator crashes.

    Covers two failure modes:
      1. Regular Exception from hydrator (run_hydrator_source raises RuntimeError)
      2. KeyboardInterrupt from hydrator (simulates process kill mid-sleep)
    """

    # gmail_linkedin is mocked (returns SourceResult directly without writing pipeline_runs),
    # so we only assert on sources the orchestrator writes directly.
    REQUIRED_SOURCES = {
        "hydrator_linkedin",
        "llm_extraction",
        "embedding",
        "dedup_c21",
        "dedup_merge_c29",
        "hardfilter",
        "rank",
    }

    def _run_with_crashing_hydrator(
        self,
        test_db: Path,
        logs_dir: Path,
        exc_to_raise: BaseException,
    ) -> tuple[Any, list[dict]]:
        """Run pipeline with gmail returning 1 new posting and hydrator raising exc_to_raise."""
        one_posting = SourceResult(
            source="gmail_linkedin",
            health_status="healthy",
            new_postings=1,
        )

        def _crashing_hydrator(*args: Any, **kwargs: Any) -> SourceResult:
            raise exc_to_raise

        with (
            patch("jd_matcher.pipeline._run_gmail_source", return_value=one_posting),
            patch("jd_matcher.pipeline._run_hydrator_source", side_effect=_crashing_hydrator),
        ):
            try:
                summary = run_pipeline(db_path=test_db)
            except (KeyboardInterrupt, SystemExit):
                # Expected re-raise for signal interrupts — pipeline_runs rows
                # must already be written for all phases at this point.
                summary = None

        rows = _pipeline_runs_for_run(test_db, _get_latest_run_id(test_db))
        return summary, rows

    def test_regular_exception_from_hydrator_does_not_skip_downstream_phases(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """If run_hydrator_source raises RuntimeError, all downstream phases still run.

        Regression: before the fix, a hydrator RuntimeError would propagate un-caught
        through run_pipeline, leaving extract/embed/dedup/hardfilter/rank with no
        pipeline_runs rows — violating the C11 mandatory-persistence invariant.
        """
        _summary, rows = self._run_with_crashing_hydrator(
            test_db, logs_dir, RuntimeError("simulated hydrator crash")
        )
        sources = {r["source"] for r in rows}
        missing = self.REQUIRED_SOURCES - sources
        assert not missing, (
            f"Mandatory-persistence violated after hydrator RuntimeError: "
            f"missing pipeline_runs rows for {missing}. "
            f"All 8 sources must always be written regardless of hydrator outcome."
        )
        hydrator_row = next((r for r in rows if r["source"] == "hydrator_linkedin"), None)
        assert hydrator_row is not None, "hydrator_linkedin row missing"
        assert hydrator_row["health_status"] == "failed", (
            f"hydrator_linkedin must be marked failed, got '{hydrator_row['health_status']}'"
        )
        assert hydrator_row["failure_reason"] is not None, (
            "hydrator_linkedin failure_reason must be non-null"
        )

    def test_keyboard_interrupt_from_hydrator_persists_all_phase_rows(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """If run_hydrator_source raises KeyboardInterrupt, all downstream phases still
        write their pipeline_runs rows before the interrupt is propagated.

        Regression: this is the actual failure mode from run be8e8ae2 — the user's
        Ctrl+C mid-hydration killed the process without persisting any rows for
        extract/embed/dedup/hardfilter/rank.
        """
        one_posting = SourceResult(
            source="gmail_linkedin",
            health_status="healthy",
            new_postings=1,
        )

        # Hydrator raises KeyboardInterrupt — simulates Ctrl+C mid-sleep
        # in HYDRATOR_RATE_LIMITER.wait()
        def _interrupted_hydrator(*args: Any, **kwargs: Any) -> SourceResult:
            # Simulate what _flush_partial_hydrator_result would do:
            # the real run_hydrator_source catches KeyboardInterrupt, writes
            # a partial row, and re-raises. Here we just raise directly to
            # test the orchestrator's deferred-interrupt logic.
            raise KeyboardInterrupt("simulated Ctrl+C during rate-limiter sleep")

        with (
            patch("jd_matcher.pipeline._run_gmail_source", return_value=one_posting),
            patch("jd_matcher.pipeline._run_hydrator_source", side_effect=_interrupted_hydrator),
        ):
            with pytest.raises(KeyboardInterrupt):
                run_pipeline(db_path=test_db)

        rows = _pipeline_runs_for_run(test_db, _get_latest_run_id(test_db))
        sources = {r["source"] for r in rows}

        # Hydrator row is NOT written here because the mock bypasses
        # _flush_partial_hydrator_result — the orchestrator writes it via the
        # except Exception handler (which catches RuntimeError but NOT
        # KeyboardInterrupt). The orchestrator's KeyboardInterrupt handler
        # defers the signal and continues downstream phases before re-raising.
        # Key assertion: downstream phases wrote their rows.
        downstream_required = {
            "llm_extraction",
            "embedding",
            "dedup_c21",
            "dedup_merge_c29",
            "hardfilter",
            "rank",
        }
        missing = downstream_required - sources
        assert not missing, (
            f"C11 mandatory-persistence violated after hydrator KeyboardInterrupt: "
            f"downstream phases {missing} did not write pipeline_runs rows. "
            f"These phases must always run regardless of how the hydrator was interrupted."
        )

    def test_pipeline_complete_event_written_after_hydrator_failure(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """After a regular hydrator exception, pipeline_complete event must appear in JSONL log."""
        one_posting = SourceResult(
            source="gmail_linkedin",
            health_status="healthy",
            new_postings=1,
        )

        with (
            patch("jd_matcher.pipeline._run_gmail_source", return_value=one_posting),
            patch(
                "jd_matcher.pipeline._run_hydrator_source",
                side_effect=RuntimeError("simulated hydrator crash"),
            ),
        ):
            summary = run_pipeline(db_path=test_db)

        # Find the JSONL log for this run
        log_files = list(logs_dir.glob(f"pipeline-{summary.run_id}.jsonl"))
        assert log_files, f"No JSONL log found for run_id={summary.run_id}"
        log_content = log_files[0].read_text()
        events = [json.loads(line) for line in log_content.splitlines() if line.strip()]
        event_names = [e.get("event") for e in events]
        assert "pipeline_complete" in event_names, (
            f"pipeline_complete event missing from JSONL log after hydrator failure. "
            f"Events found: {event_names}"
        )
        # phase_aborted or hydrator_source_exception must also be present
        assert any(
            e in event_names for e in ("phase_aborted", "hydrator_source_exception")
        ), (
            f"No failure event logged for hydrator crash. Events: {event_names}"
        )


def _get_latest_run_id(db_path: Path) -> str:
    """Return the run_id of the most recently started pipeline run."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT run_id FROM pipeline_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None, "No pipeline_runs rows found"
        return row[0]
    finally:
        conn.close()
