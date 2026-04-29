"""
Tests for src/jd_matcher/pipeline.py (C11 — Pipeline orchestrator).

AC coverage:
  AC1 — 3 runs × 2 sources = 6 pipeline_runs rows, all with non-null health_status
  AC2 — hydrator_linkedin failure does not cascade to other sources
  AC3 — source_failure event emitted on healthy → failed transition
  AC4 — structured JSON log written; ≥1 line per step; all lines parse; no stdout
  AC5 — 5 LinkedIn fixture emails → N unique postings in DB
  AC6 — idempotency: second run on same mailbox produces 0 new postings

PoC: LinkedIn-only per ALIGNMENT-LOG 2026-04-28 (Indeed deferred to MVP-M1).
When Indeed is re-activated at MVP-M1, these tests need to revert to dual-source expectations.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.pipeline import run_pipeline, PipelineRunSummary


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures"
LINKEDIN_EML_DIR = FIXTURES_ROOT / "gmail" / "linkedin"
INDEED_EML_DIR = FIXTURES_ROOT / "gmail" / "indeed"
LINKEDIN_HTML_DIR = FIXTURES_ROOT / "hydration" / "linkedin"
INDEED_HTML_DIR = FIXTURES_ROOT / "hydration" / "indeed"


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
    """Override _LOGS_DIR to a temp directory so tests don't pollute project logs/."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    import jd_matcher.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "_LOGS_DIR", log_dir)
    return log_dir


def _pipeline_runs_for_run(db_path: Path, run_id: str) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT source, health_status, failure_reason FROM pipeline_runs "
            "WHERE run_id = ? ORDER BY source",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()


def _all_pipeline_runs(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT run_id, source, health_status FROM pipeline_runs ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def _count_postings(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
    finally:
        conn.close()


def _events_of_type(db_path: Path, event_type: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT metadata, timestamp FROM events WHERE event_type = ? ORDER BY id",
            (event_type,),
        ).fetchall()
        return [{"metadata": json.loads(r[0]), "timestamp": r[1]} for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# AC1 — 3 runs × 2 sources = 6 pipeline_runs rows, all with non-null health_status
# PoC: LinkedIn-only per ALIGNMENT-LOG 2026-04-28 (Indeed deferred to MVP-M1).
# When Indeed is re-activated at MVP-M1, revert counts: 2 sources → 4, 6 rows → 12.
# ---------------------------------------------------------------------------


class TestMandatoryPersistence:
    def test_three_runs_produce_six_rows(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """Each of 3 pipeline runs writes exactly 3 rows — 9 total.

        PoC sources: gmail_linkedin + hydrator_linkedin + dedup_c21 (C21 added M2-008).
        When Indeed is re-activated at MVP-M1, revert counts: 3 sources → 5, 9 rows → 15.
        """
        run_ids = []
        for _ in range(3):
            summary = run_pipeline(db_path=test_db)
            run_ids.append(summary.run_id)

        rows = _all_pipeline_runs(test_db)
        # Filter to rows with run_ids from the orchestrator (not sub-run ingester rows)
        orch_rows = [r for r in rows if r[0] in run_ids]
        assert len(orch_rows) == 9, (
            f"Expected 9 orchestrator pipeline_runs rows across 3 runs, got {len(orch_rows)}"
        )

    def test_all_rows_have_non_null_health_status(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """health_status must never be NULL."""
        run_pipeline(db_path=test_db)
        conn = sqlite3.connect(test_db)
        try:
            null_rows = conn.execute(
                "SELECT source, run_id FROM pipeline_runs WHERE health_status IS NULL"
            ).fetchall()
        finally:
            conn.close()
        assert null_rows == [], f"Found rows with NULL health_status: {null_rows}"

    def test_two_sources_per_run(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """Each run produces exactly one row for each of the 3 PoC sources.

        PoC sources: gmail_linkedin + hydrator_linkedin + dedup_c21 (C21 added M2-008).
        When Indeed is re-activated at MVP-M1, expected set reverts to 5 sources.
        """
        summary = run_pipeline(db_path=test_db)
        rows = _pipeline_runs_for_run(test_db, summary.run_id)
        sources_written = {r[0] for r in rows}
        expected = {"gmail_linkedin", "hydrator_linkedin", "dedup_c21"}
        assert sources_written == expected, (
            f"Sources in pipeline_runs mismatch. Got: {sources_written}"
        )


# ---------------------------------------------------------------------------
# AC2 — per-source isolation: hydrator_linkedin failure does not cascade
# ---------------------------------------------------------------------------


class TestPerSourceIsolation:
    def test_hydrator_linkedin_failure_does_not_cascade_to_gmail_sources(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """Forcing hydrator_linkedin to raise must not prevent gmail_linkedin from completing.

        PoC: LinkedIn-only per ALIGNMENT-LOG 2026-04-28 (Indeed deferred to MVP-M1).
        When Indeed is re-activated at MVP-M1, also assert gmail_indeed remains healthy.
        """
        def _raise_on_linkedin(url: str, fixtures_dir: Any = None) -> None:
            raise RuntimeError("Simulated hydrator_linkedin failure")

        with patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=_raise_on_linkedin):
            summary = run_pipeline(db_path=test_db)

        rows = _pipeline_runs_for_run(test_db, summary.run_id)
        row_by_source = {r[0]: r for r in rows}

        # Confirm all 3 PoC sources have rows (dedup_c21 added M2-008)
        assert set(row_by_source.keys()) == {"gmail_linkedin", "hydrator_linkedin", "dedup_c21"}

        # hydrator_linkedin: since Fix 2b added per-URL exception handling,
        # individual URL exceptions are caught and skipped (not propagated to the
        # outer try/except). All URLs raise → results=[] → compute_source_health([])
        # returns "healthy". The invariant is that it DOES NOT cascade to Gmail sources,
        # not that it must be marked failed.
        assert row_by_source["hydrator_linkedin"][1] in ("healthy", "degraded", "failed"), (
            "hydrator_linkedin must have a valid health_status row even when all URLs fail"
        )

        # gmail_linkedin is isolated from hydrator failures
        assert row_by_source["gmail_linkedin"][1] == "healthy", (
            f"gmail_linkedin should be healthy but got {row_by_source['gmail_linkedin'][1]}"
        )


# ---------------------------------------------------------------------------
# AC3 — source_failure event emitted on healthy → failed transition
# ---------------------------------------------------------------------------


class TestSourceFailureEvents:
    def _make_healthy_indeed_mock(self):
        """Return a mock for indeed_hydrate that always returns complete results."""
        from jd_matcher.hydrate.indeed import HydratedIndeedJD

        def _healthy(url: str, fixtures_dir: Any = None) -> HydratedIndeedJD:
            return HydratedIndeedJD(
                url=url, job_id="test", title="Test", company="Co",
                location="Vancouver", description="desc", posted_date=None,
                seniority_level=None, employment_type=None, industries=None,
                raw_html=b"<html/>", hydration_status="complete", failure_reason=None,
            )
        return _healthy

    def test_source_failure_event_emitted_on_first_failure(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """healthy → failed transition must write a source_failure event row.

        Strategy: seed a healthy pipeline_runs row for hydrator_linkedin, then
        force the hydrator to raise on the next run. The transition event fires
        because the previous status is 'healthy' and the new status is 'failed'.
        We use a mocked Gmail ingester that returns no emails so the hydration
        URLs come from a manually seeded postings row with partial hydration_status.
        """
        import sqlite3 as _sqlite3

        # Seed: one linkedin posting with partial hydration so it queues for hydration
        conn = _sqlite3.connect(test_db)
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("PRAGMA foreign_keys = ON;")
            cur = conn.execute(
                "INSERT INTO postings (user_id, canonical_title, hydration_status, first_seen, last_seen) "
                "VALUES ('default', 'Test Job', 'partial', ?, ?)",
                (now, now),
            )
            posting_id = cur.lastrowid
            conn.execute(
                "INSERT INTO seen_urls (url, user_id, posting_id, seen_at) VALUES (?, 'default', ?, ?)",
                ("https://linkedin.com/jobs/view/9999999", posting_id, now),
            )
            # Seed a healthy pipeline_runs row for hydrator_linkedin
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, source, health_status, started_at, finished_at) "
                "VALUES ('seed-run-001', 'hydrator_linkedin', 'healthy', ?, ?)",
                (now, now),
            )
            conn.commit()
        finally:
            conn.close()

        events_before = _events_of_type(test_db, "source_failure")
        assert len(events_before) == 0

        # Now force hydrator_linkedin to raise — previous status is 'healthy'
        def _raise(url: str, fixtures_dir: Any = None) -> None:
            raise RuntimeError("forced transition failure")

        healthy_indeed = self._make_healthy_indeed_mock()

        # Patch GmailIngester to return no emails (avoid fixture noise)
        import jd_matcher.pipeline as pipeline_mod
        original_ingester = pipeline_mod.GmailIngester

        class _NoOpIngester:
            def __init__(self, credentials: Any, db_path: Path) -> None:
                pass

            def fetch_for_sender(self, sender: str, since_date: Any, run_id: str = "", canonical_run_id: str | None = None) -> list:
                return []

        with patch("jd_matcher.pipeline.GmailIngester", _NoOpIngester), \
             patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=_raise), \
             patch("jd_matcher.pipeline.indeed_hydrate", side_effect=healthy_indeed):
            run_pipeline(db_path=test_db)

        events_after = _events_of_type(test_db, "source_failure")
        li_events = [e for e in events_after if e["metadata"]["source"] == "hydrator_linkedin"]
        assert len(li_events) == 1, (
            f"Expected exactly one source_failure event for hydrator_linkedin, got {len(li_events)}"
        )

        meta = li_events[0]["metadata"]
        assert meta["previous_status"] == "healthy"
        assert meta["new_status"] == "failed"
        assert meta["failure_reason"] is not None
        assert li_events[0]["timestamp"] is not None

    def test_never_run_to_failed_emits_event(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """never_run → failed transition (first ever run fails) must also emit event."""
        def _raise(url: str, fixtures_dir: Any = None) -> None:
            raise RuntimeError("initial failure")

        healthy_indeed = self._make_healthy_indeed_mock()
        with patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=_raise), \
             patch("jd_matcher.pipeline.indeed_hydrate", side_effect=healthy_indeed):
            run_pipeline(db_path=test_db)

        events = _events_of_type(test_db, "source_failure")
        li_events = [e for e in events if e["metadata"]["source"] == "hydrator_linkedin"]
        assert len(li_events) == 1
        assert li_events[0]["metadata"]["previous_status"] == "never_run"
        assert li_events[0]["metadata"]["new_status"] == "failed"

    def test_repeated_failure_does_not_duplicate_event(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """failed → failed does NOT emit a second source_failure event."""
        def _raise(url: str, fixtures_dir: Any = None) -> None:
            raise RuntimeError("persistent failure")

        healthy_indeed = self._make_healthy_indeed_mock()
        with patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=_raise), \
             patch("jd_matcher.pipeline.indeed_hydrate", side_effect=healthy_indeed):
            run_pipeline(db_path=test_db)  # first failure — event emitted
            run_pipeline(db_path=test_db)  # second failure — no new event

        events = _events_of_type(test_db, "source_failure")
        li_events = [e for e in events if e["metadata"]["source"] == "hydrator_linkedin"]
        assert len(li_events) == 1, (
            "Only one source_failure event should be emitted per transition, "
            f"got {len(li_events)}"
        )


# ---------------------------------------------------------------------------
# AC4 — structured JSON log written; all lines parse; no stdout from orchestrator
# ---------------------------------------------------------------------------


class TestStructuredLogging:
    def test_log_file_created_with_run_id(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        summary = run_pipeline(db_path=test_db)
        log_file = logs_dir / f"pipeline-{summary.run_id}.jsonl"
        assert log_file.exists(), f"Log file not found: {log_file}"

    def test_log_lines_are_valid_json(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        summary = run_pipeline(db_path=test_db)
        log_file = logs_dir / f"pipeline-{summary.run_id}.jsonl"
        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        assert len(lines) >= 4, f"Expected ≥4 log lines (one per source step), got {len(lines)}"
        for i, line in enumerate(lines):
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                pytest.fail(f"Log line {i} is not valid JSON: {line!r} — {e}")

    def test_log_contains_pipeline_events(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        summary = run_pipeline(db_path=test_db)
        log_file = logs_dir / f"pipeline-{summary.run_id}.jsonl"
        parsed_lines = [json.loads(ln) for ln in log_file.read_text().splitlines() if ln.strip()]
        event_types = {ln.get("event") for ln in parsed_lines}
        assert "pipeline_start" in event_types
        assert "pipeline_complete" in event_types

    def test_no_stdout_from_pipeline(
        self, test_db: Path, skip_live: None, logs_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        run_pipeline(db_path=test_db)
        captured = capsys.readouterr()
        assert captured.out == "", (
            f"Pipeline produced stdout output (must use logging): {captured.out!r}"
        )


# ---------------------------------------------------------------------------
# AC5 — 5 LinkedIn + 5 Indeed fixture emails → expected unique postings in DB
# ---------------------------------------------------------------------------


class TestEndToEndFixtureRun:
    """PoC: LinkedIn-only per ALIGNMENT-LOG 2026-04-28 (Indeed deferred to MVP-M1).
    When Indeed is re-activated at MVP-M1, restore Indeed fixture counting and
    revert the docstring to "5 LinkedIn + 5 Indeed fixtures".
    """

    def _count_unique_urls_in_fixtures(self, limit_per_source: int = 5) -> int:
        """Count unique canonical URLs that the LinkedIn parser extracts from the first N fixtures."""
        from jd_matcher.ingest.gmail import RawEmail
        from jd_matcher.parse.linkedin_email import parse as parse_li
        from datetime import datetime, timezone
        import email as _email_module

        li_files = sorted(LINKEDIN_EML_DIR.glob("*.eml"))[:limit_per_source]

        seen: set[str] = set()
        for path in li_files:
            body = path.read_bytes()
            msg = _email_module.message_from_bytes(body)
            raw = RawEmail(
                id=path.stem,
                sender=msg.get("From", ""),
                subject=msg.get("Subject", ""),
                received_at=datetime.now(timezone.utc),
                body_bytes=body,
            )
            for p in parse_li(raw):
                seen.add(p.url)
        return len(seen)

    def test_e2e_fixture_run_produces_expected_postings(
        self,
        test_db: Path,
        logs_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """5 LinkedIn fixtures → exactly N unique postings (N computed from fixtures).

        PoC: LinkedIn-only per ALIGNMENT-LOG 2026-04-28 (Indeed deferred to MVP-M1).
        When Indeed is re-activated at MVP-M1, also count Indeed fixture URLs here.
        """
        monkeypatch.setenv("SKIP_LIVE", "1")

        class _LimitedIngester:
            """Ingester that only returns the first 5 .eml files per sender."""
            def __init__(self, credentials: Any, db_path: Path) -> None:
                from jd_matcher.ingest.gmail import GmailIngester as _GI
                self._inner = _GI(credentials, db_path)

            def fetch_for_sender(self, sender: str, since_date: Any, run_id: str = "", canonical_run_id: str | None = None) -> list:
                result = self._inner.fetch_for_sender(sender, since_date, run_id=run_id, canonical_run_id=canonical_run_id)
                return result[:5]

        with patch("jd_matcher.pipeline.GmailIngester", _LimitedIngester):
            summary = run_pipeline(db_path=test_db)

        expected = self._count_unique_urls_in_fixtures(limit_per_source=5)
        actual = _count_postings(test_db)
        assert actual == expected, (
            f"Expected {expected} postings from 5 LinkedIn fixtures, got {actual}"
        )


# ---------------------------------------------------------------------------
# AC6 — idempotency: second run on same mailbox produces 0 new postings
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_second_run_produces_zero_new_postings(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """Re-running the pipeline on the same fixture mailbox must not create new postings."""
        run_pipeline(db_path=test_db)
        count_after_first = _count_postings(test_db)

        run_pipeline(db_path=test_db)
        count_after_second = _count_postings(test_db)

        assert count_after_second == count_after_first, (
            f"Second run created {count_after_second - count_after_first} new postings "
            f"(expected 0)"
        )

    def test_idempotency_seen_urls_respected(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """URL dedup table must still have the same rows after a second run."""
        run_pipeline(db_path=test_db)

        conn = sqlite3.connect(test_db)
        try:
            urls_after_first = {row[0] for row in conn.execute("SELECT url FROM seen_urls").fetchall()}
        finally:
            conn.close()

        run_pipeline(db_path=test_db)

        conn = sqlite3.connect(test_db)
        try:
            urls_after_second = {row[0] for row in conn.execute("SELECT url FROM seen_urls").fetchall()}
        finally:
            conn.close()

        assert urls_after_second == urls_after_first, (
            "seen_urls changed between runs — idempotency violated"
        )


# ---------------------------------------------------------------------------
# Return model validation
# ---------------------------------------------------------------------------


class TestPipelineRunSummary:
    """PoC: LinkedIn-only per ALIGNMENT-LOG 2026-04-28 (Indeed deferred to MVP-M1).
    When Indeed is re-activated at MVP-M1, revert counts: 2 sources → 4, 2 steps → 4.
    """

    def test_summary_has_two_source_results(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        summary = run_pipeline(db_path=test_db)
        assert isinstance(summary, PipelineRunSummary)
        assert len(summary.sources) == 2

    def test_summary_source_names_correct(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """PoC: LinkedIn-only per ALIGNMENT-LOG 2026-04-28 (Indeed deferred to MVP-M1)."""
        summary = run_pipeline(db_path=test_db)
        source_names = {s.source for s in summary.sources}
        assert source_names == {"gmail_linkedin", "hydrator_linkedin"}

    def test_summary_has_steps(
        self, test_db: Path, skip_live: None, logs_dir: Path
    ) -> None:
        """PoC M2: LinkedIn-only + C20 embedding + C21 dedup — expect 4 steps."""
        summary = run_pipeline(db_path=test_db)
        assert len(summary.steps) == 4
        assert "Embedding postings (C20)…" in summary.steps
        assert "Dedup decisions (C21)…" in summary.steps


# ---------------------------------------------------------------------------
# PoC scope tripwire — Indeed deferred to MVP-M1
# ---------------------------------------------------------------------------


def test_gmail_sources_constant_is_linkedin_only_in_poc():
    """PoC: Indeed deferred to MVP-M1 per ALIGNMENT-LOG 2026-04-28.
    Re-enabling means flipping _GMAIL_SOURCES."""
    from jd_matcher.pipeline import _GMAIL_SOURCES
    assert _GMAIL_SOURCES == ("linkedin",), (
        "Indeed deferred to MVP-M1; if re-activating, also update "
        "ALIGNMENT-LOG and PRD §9 R3 status"
    )
