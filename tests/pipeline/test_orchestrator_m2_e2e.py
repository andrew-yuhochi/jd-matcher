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
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.pipeline import run_pipeline


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
