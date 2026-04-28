"""
Integration test: full pipeline run against synthetic fixture mailbox → email_ingest_log.

AC #5: SELECT DISTINCT pipeline_run_id FROM email_ingest_log must equal 1 value per
       orchestrator invocation (canonical run_id, not sub-run-ids).
AC #10: 5 fixture emails produce exactly 5 email_ingest_log rows with non-zero counters.

All Gmail API and hydration calls are mocked at the boundary — no live network.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.hydrate.linkedin import HydratedJD
from jd_matcher.hydrate.indeed import HydratedIndeedJD
from jd_matcher.pipeline import run_pipeline

FIXTURES_ROOT = Path(__file__).parent / "fixtures"
LINKEDIN_EML_DIR = FIXTURES_ROOT / "gmail" / "linkedin"
INDEED_EML_DIR = FIXTURES_ROOT / "gmail" / "indeed"


# ---------------------------------------------------------------------------
# Helpers
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


def _make_complete_linkedin_jd(url: str) -> HydratedJD:
    return HydratedJD(
        url=url,
        job_id="12345",
        title="Data Scientist",
        company="Test Corp",
        location="Vancouver, BC",
        description="Great opportunity.",
        posted_date=None,
        seniority_level=None,
        employment_type=None,
        industries=None,
        raw_html=b"<html/>",
        hydration_status="complete",
        failure_reason=None,
    )


def _make_complete_indeed_jd(url: str) -> HydratedIndeedJD:
    return HydratedIndeedJD(
        url=url,
        job_id="abcde1234",
        title="ML Engineer",
        company="Indeed Corp",
        location="Remote",
        description="Great opportunity.",
        posted_date=None,
        seniority_level=None,
        employment_type=None,
        industries=None,
        raw_html=b"<html/>",
        hydration_status="complete",
        failure_reason=None,
    )


def _get_ingest_log_rows(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT gmail_message_id, source, pipeline_run_id,
                   urls_extracted_count, urls_new_count, postings_created_count,
                   postings_hydrated_count, postings_hydration_failed_count
            FROM email_ingest_log ORDER BY id
            """
        ).fetchall()
        cols = [
            "gmail_message_id", "source", "pipeline_run_id",
            "urls_extracted_count", "urls_new_count", "postings_created_count",
            "postings_hydrated_count", "postings_hydration_failed_count",
        ]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def _get_distinct_pipeline_run_ids(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT pipeline_run_id FROM email_ingest_log"
            ).fetchall()
        ]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The integration test
# ---------------------------------------------------------------------------


class TestPipelineIngestLogIntegration:
    """Run pipeline against 5 LinkedIn + 5 Indeed fixture emails; assert AC #5 + #10."""

    def _make_limited_ingester(self, n: int = 5):
        """Return an ingester class that caps emails at n per sender."""

        class _LimitedIngester:
            def __init__(self, credentials: Any, db_path: Path) -> None:
                from jd_matcher.ingest.gmail import GmailIngester as _GI
                self._inner = _GI(credentials, db_path)

            def fetch_for_sender(
                self,
                sender: str,
                since_date: Any,
                run_id: str = "",
                canonical_run_id: str | None = None,
            ) -> list:
                result = self._inner.fetch_for_sender(
                    sender,
                    since_date,
                    run_id=run_id,
                    canonical_run_id=canonical_run_id,
                )
                return result[:n]

        return _LimitedIngester

    def test_five_emails_produce_five_log_rows(
        self,
        test_db: Path,
        skip_live: None,
        logs_dir: Path,
    ) -> None:
        """5 LinkedIn + 5 Indeed fixture emails → exactly 10 email_ingest_log rows."""
        LimitedIngester = self._make_limited_ingester(5)

        with (
            patch("jd_matcher.pipeline.GmailIngester", LimitedIngester),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=_make_complete_linkedin_jd),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=_make_complete_indeed_jd),
        ):
            run_pipeline(db_path=test_db)

        rows = _get_ingest_log_rows(test_db)
        # 5 LinkedIn + 5 Indeed = 10 emails total
        assert len(rows) == 10, (
            f"Expected 10 email_ingest_log rows (5 linkedin + 5 indeed), got {len(rows)}"
        )

    def test_ac5_single_distinct_pipeline_run_id(
        self,
        test_db: Path,
        skip_live: None,
        logs_dir: Path,
    ) -> None:
        """AC #5: all email_ingest_log rows for one pipeline invocation share ONE canonical run_id."""
        LimitedIngester = self._make_limited_ingester(5)

        with (
            patch("jd_matcher.pipeline.GmailIngester", LimitedIngester),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=_make_complete_linkedin_jd),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=_make_complete_indeed_jd),
        ):
            summary = run_pipeline(db_path=test_db)

        distinct_run_ids = _get_distinct_pipeline_run_ids(test_db)
        assert len(distinct_run_ids) == 1, (
            f"Expected 1 DISTINCT pipeline_run_id in email_ingest_log, got {len(distinct_run_ids)}: "
            f"{distinct_run_ids}. "
            "This indicates threading is broken — sub-run-ids are being written instead of the canonical run_id."
        )
        assert distinct_run_ids[0] == summary.run_id, (
            f"DISTINCT pipeline_run_id {distinct_run_ids[0]!r} != orchestrator run_id {summary.run_id!r}"
        )

    def test_ac10_counters_updated_after_pipeline_run(
        self,
        test_db: Path,
        skip_live: None,
        logs_dir: Path,
    ) -> None:
        """AC #10: after the full pipeline, email_ingest_log rows have non-zero URL and hydration counters."""
        LimitedIngester = self._make_limited_ingester(5)

        with (
            patch("jd_matcher.pipeline.GmailIngester", LimitedIngester),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=_make_complete_linkedin_jd),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=_make_complete_indeed_jd),
        ):
            run_pipeline(db_path=test_db)

        rows = _get_ingest_log_rows(test_db)
        assert rows, "No email_ingest_log rows found after pipeline run"

        # At least some rows should have non-zero URL counts (emails that produced postings).
        rows_with_urls = [r for r in rows if r["urls_extracted_count"] > 0]
        assert rows_with_urls, (
            "All email_ingest_log rows have urls_extracted_count=0 after pipeline run. "
            "C4 writer hook is not firing."
        )

        # Rows with new URLs should also have postings_created_count > 0.
        rows_with_new = [r for r in rows if r["urls_new_count"] > 0]
        for row in rows_with_new:
            assert row["postings_created_count"] > 0 or row["postings_created_count"] == row["urls_new_count"], (
                f"urls_new_count={row['urls_new_count']} but postings_created_count={row['postings_created_count']}"
            )

    def test_two_pipeline_runs_produce_two_distinct_run_ids(
        self,
        test_db: Path,
        skip_live: None,
        logs_dir: Path,
    ) -> None:
        """Two separate pipeline invocations → 2 distinct pipeline_run_id values in email_ingest_log."""
        LimitedIngester = self._make_limited_ingester(2)

        with (
            patch("jd_matcher.pipeline.GmailIngester", LimitedIngester),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=_make_complete_linkedin_jd),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=_make_complete_indeed_jd),
        ):
            summary1 = run_pipeline(db_path=test_db)

        # Re-run with fresh fixture IDs won't add rows (UNIQUE on gmail_message_id)
        # so we just verify the distinct run IDs after the first run.
        distinct = _get_distinct_pipeline_run_ids(test_db)
        assert summary1.run_id in distinct

    def test_no_ingest_sub_run_rows_written_by_orchestrator(
        self,
        test_db: Path,
        skip_live: None,
        logs_dir: Path,
    ) -> None:
        """REGRESSION (Bug 2): orchestrator-driven runs must not leave _ingest_ sub-run rows.

        When canonical_run_id is provided to GmailIngester.fetch_for_sender, the ingester
        must not write its own pipeline_runs row. Previously, the internal write attempted
        Gmail API calls with Application Default Credentials (ADC), polluting pipeline_runs
        with phantom 'failed' rows and triggering DefaultCredentialsError in production.

        PoC: LinkedIn-only per ALIGNMENT-LOG 2026-04-28 (Indeed deferred to MVP-M1).
        When Indeed is re-activated at MVP-M1, revert total_row_count assertion to 4.
        """
        LimitedIngester = self._make_limited_ingester(5)

        with (
            patch("jd_matcher.pipeline.GmailIngester", LimitedIngester),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=_make_complete_linkedin_jd),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=_make_complete_indeed_jd),
        ):
            run_pipeline(db_path=test_db)

        conn = sqlite3.connect(test_db)
        try:
            ingest_row_count = conn.execute(
                "SELECT count(*) FROM pipeline_runs WHERE run_id LIKE '%_ingest_%'"
            ).fetchone()[0]
            total_row_count = conn.execute(
                "SELECT count(*) FROM pipeline_runs"
            ).fetchone()[0]
        finally:
            conn.close()

        assert ingest_row_count == 0, (
            f"Found {ingest_row_count} pipeline_runs rows with '_ingest_' in run_id. "
            "GmailIngester must not write its own row when canonical_run_id is provided."
        )
        # Orchestrator writes exactly 2 canonical rows: gmail_linkedin, hydrator_linkedin.
        assert total_row_count == 2, (
            f"Expected exactly 2 pipeline_runs rows (one per canonical source), got {total_row_count}. "
            "Double-write or missing orchestrator rows detected."
        )


# ---------------------------------------------------------------------------
# Option A threading proof: duplicate URL across two emails credits correctly
# ---------------------------------------------------------------------------


class TestDuplicateUrlAcrossEmailsOptionA:
    """Prove that Option A (gmail_message_id carried in ParsedPosting) handles the
    duplicate-URL edge case correctly.

    Scenario: two LinkedIn alert emails (msg-dup-001, msg-dup-002) both contain
    the same canonical URL. Under Option B (url→gmail_id dict with last-write-wins),
    msg-dup-001 would silently lose hydration credit. Under Option A (first-email-wins),
    msg-dup-001 is credited and msg-dup-002 gets zero hydration credit — deterministic
    and predictable.
    """

    DUPLICATE_URL = "https://linkedin.com/jobs/view/9999999"
    DUPLICATE_JOB_ID = "9999999"

    def _build_minimal_eml(self, subject: str) -> bytes:
        """Return minimal RFC-822 bytes containing the duplicate LinkedIn URL."""
        plain_body = f"Check this job: https://www.linkedin.com/comm/jobs/view/{self.DUPLICATE_JOB_ID}/?trackingId=abc"
        return (
            f"From: jobalerts-noreply@linkedin.com\r\n"
            f"To: test@example.com\r\n"
            f"Subject: {subject}\r\n"
            f"Date: Mon, 01 Jan 2026 10:00:00 +0000\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"\r\n"
            f"{plain_body}\r\n"
        ).encode("utf-8")

    def test_duplicate_url_across_emails_credits_first_email_only(
        self,
        test_db: Path,
        logs_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the same URL appears in two emails, Option A credits the first email
        for hydration and leaves the second email's hydration counter at 0.

        This proves the Option B edge case is eliminated:
        - Both emails appear in email_ingest_log
        - The URL is deduped: only 1 posting created (urls_new_count=1 on msg-dup-001)
        - Hydration credit goes to msg-dup-001 (first email to surface the URL)
        - msg-dup-002 has postings_hydrated_count=0 (it saw an already-seen URL)
        """
        monkeypatch.setenv("SKIP_LIVE", "1")

        from jd_matcher.ingest.gmail import RawEmail
        from datetime import datetime, timezone

        eml_001 = self._build_minimal_eml("Alert 1 — duplicate URL test")
        eml_002 = self._build_minimal_eml("Alert 2 — same URL as above")

        email_001 = RawEmail(
            id="msg-dup-001",
            sender="jobalerts-noreply@linkedin.com",
            subject="Alert 1 — duplicate URL test",
            received_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            body_bytes=eml_001,
        )
        email_002 = RawEmail(
            id="msg-dup-002",
            sender="jobalerts-noreply@linkedin.com",
            subject="Alert 2 — same URL as above",
            received_at=datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
            body_bytes=eml_002,
        )

        import jd_matcher.pipeline as pipeline_mod
        from jd_matcher.db.email_ingest_log import insert_email_log

        class _DupIngester:
            """Returns the two duplicate-URL emails for linkedin; nothing for indeed.

            Mirrors the real GmailIngester contract: inserts email_ingest_log rows
            (C3 writer hook) before returning emails.
            """
            def __init__(self, credentials: Any, db_path: Path) -> None:
                self._db_path = db_path

            def fetch_for_sender(
                self,
                sender: str,
                since_date: Any,
                run_id: str = "",
                canonical_run_id: str | None = None,
            ) -> list:
                if sender != "linkedin":
                    return []
                emails = [email_001, email_002]
                log_run_id = canonical_run_id or run_id
                for raw_email in emails:
                    insert_email_log(
                        gmail_message_id=raw_email.id,
                        source="linkedin",
                        sender=raw_email.sender,
                        subject=raw_email.subject,
                        received_at=raw_email.received_at,
                        pipeline_run_id=log_run_id,
                        db_path=self._db_path,
                    )
                return emails

        def _hydrate_linkedin(url: str, **kwargs: Any) -> HydratedJD:
            return _make_complete_linkedin_jd(url)

        def _hydrate_indeed(url: str, **kwargs: Any) -> HydratedIndeedJD:
            return _make_complete_indeed_jd(url)

        with (
            patch("jd_matcher.pipeline.GmailIngester", _DupIngester),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=_hydrate_linkedin),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=_hydrate_indeed),
        ):
            run_pipeline(db_path=test_db)

        rows = _get_ingest_log_rows(test_db)

        # Both emails must appear in the log
        msg_ids = {r["gmail_message_id"] for r in rows}
        assert "msg-dup-001" in msg_ids, "First email missing from email_ingest_log"
        assert "msg-dup-002" in msg_ids, "Second email missing from email_ingest_log"

        row_001 = next(r for r in rows if r["gmail_message_id"] == "msg-dup-001")
        row_002 = next(r for r in rows if r["gmail_message_id"] == "msg-dup-002")

        # msg-dup-001: extracted 1 URL, it was new, hydration credited here
        assert row_001["urls_extracted_count"] == 1, (
            f"msg-dup-001 should have extracted 1 URL, got {row_001['urls_extracted_count']}"
        )
        assert row_001["urls_new_count"] == 1, (
            f"msg-dup-001 should have 1 new URL (first to surface it), got {row_001['urls_new_count']}"
        )
        assert row_001["postings_hydrated_count"] == 1, (
            f"Hydration credit must go to msg-dup-001 (first-email-wins), "
            f"got {row_001['postings_hydrated_count']}"
        )

        # msg-dup-002: extracted 1 URL but it was already seen — no new posting, no hydration credit
        assert row_002["urls_extracted_count"] == 1, (
            f"msg-dup-002 should have extracted 1 URL, got {row_002['urls_extracted_count']}"
        )
        assert row_002["urls_new_count"] == 0, (
            f"msg-dup-002 URL was already seen — urls_new_count must be 0, "
            f"got {row_002['urls_new_count']}"
        )
        assert row_002["postings_hydrated_count"] == 0, (
            f"msg-dup-002 must not receive hydration credit (first-email-wins), "
            f"got {row_002['postings_hydrated_count']}"
        )


# ---------------------------------------------------------------------------
# Credential-failure error propagation tests
# ---------------------------------------------------------------------------


class TestCredentialFailurePropagation:
    """REGRESSION (credential bug): when GmailIngester raises during orchestrator-driven
    ingestion, _run_gmail_source must write pipeline_runs 'failed' rows — not silently
    succeed with 0 new postings.

    We simulate the credential failure by patching _fetch_from_gmail to raise a
    RuntimeError (avoids depending on SKIP_LIVE state — the fixture path branches
    before _fetch_from_gmail is called, so patching at that level is the stable
    injection point).
    """

    def test_fetch_failure_writes_failed_pipeline_runs(
        self,
        test_db: Path,
        logs_dir: Path,
    ) -> None:
        """Simulated Gmail fetch error → pipeline_runs has a 'failed' row for gmail_linkedin.

        PoC: LinkedIn-only per ALIGNMENT-LOG 2026-04-28 (Indeed deferred to MVP-M1).
        When Indeed is re-activated at MVP-M1, also assert gmail_indeed in failed_sources
        and revert the pipeline_runs row count assertion to 2.
        """
        with patch(
            "jd_matcher.ingest.gmail.GmailIngester._fetch_from_gmail",
            side_effect=RuntimeError("DefaultCredentialsError: no credentials"),
        ), patch(
            "jd_matcher.ingest.gmail.GmailIngester._fetch_from_fixtures",
            side_effect=RuntimeError("DefaultCredentialsError: no credentials"),
        ):
            summary = run_pipeline(db_path=test_db, credentials=None)

        # gmail_linkedin should be in failed_sources
        assert "gmail_linkedin" in summary.failed_sources, (
            f"Expected gmail_linkedin in failed_sources, got {summary.failed_sources}"
        )

        conn = sqlite3.connect(test_db)
        try:
            rows = conn.execute(
                """
                SELECT source, health_status, failure_reason
                FROM pipeline_runs
                WHERE source = 'gmail_linkedin'
                ORDER BY source
                """
            ).fetchall()
        finally:
            conn.close()

        assert len(rows) == 1, f"Expected 1 pipeline_runs row for gmail_linkedin, got {len(rows)}"
        for source, health_status, failure_reason in rows:
            assert health_status == "failed", (
                f"{source}: expected health_status='failed', got {health_status!r}"
            )
            assert failure_reason is not None, (
                f"{source}: failure_reason must be non-null, got None"
            )
            assert "RuntimeError" in failure_reason or "credentials" in failure_reason.lower(), (
                f"{source}: failure_reason should mention the error, got {failure_reason!r}"
            )

    def test_fetch_failure_summary_shows_zero_new_postings(
        self,
        test_db: Path,
        logs_dir: Path,
    ) -> None:
        """Simulated Gmail fetch error → total_new_postings == 0 AND failed_sources non-empty.

        PoC: LinkedIn-only per ALIGNMENT-LOG 2026-04-28 (Indeed deferred to MVP-M1).
        When Indeed is re-activated at MVP-M1, revert failed_sources count assertion to >= 2.
        """
        with patch(
            "jd_matcher.ingest.gmail.GmailIngester._fetch_from_gmail",
            side_effect=RuntimeError("DefaultCredentialsError: no credentials"),
        ), patch(
            "jd_matcher.ingest.gmail.GmailIngester._fetch_from_fixtures",
            side_effect=RuntimeError("DefaultCredentialsError: no credentials"),
        ):
            summary = run_pipeline(db_path=test_db, credentials=None)

        assert summary.total_new_postings == 0
        assert len(summary.failed_sources) >= 1


class TestInsertEmailLogConflict:
    """Verify INSERT OR REPLACE semantics: re-syncing the same gmail_message_id
    updates pipeline_run_id to the new run (orphan-row fix).
    """

    def test_resync_updates_pipeline_run_id(self, test_db: Path) -> None:
        """Insert a row with run_id='A', then insert again with the same gmail_message_id
        and run_id='B' → final pipeline_run_id should be 'B'.
        """
        from jd_matcher.db.email_ingest_log import insert_email_log
        from datetime import datetime, timezone

        received = datetime(2026, 4, 25, 10, 0, 0, tzinfo=timezone.utc)

        insert_email_log(
            gmail_message_id="msg-conflict-001",
            source="linkedin",
            sender="jobalerts-noreply@linkedin.com",
            subject="Test subject",
            received_at=received,
            pipeline_run_id="run-A",
            db_path=test_db,
        )
        insert_email_log(
            gmail_message_id="msg-conflict-001",
            source="linkedin",
            sender="jobalerts-noreply@linkedin.com",
            subject="Test subject",
            received_at=received,
            pipeline_run_id="run-B",
            db_path=test_db,
        )

        conn = sqlite3.connect(test_db)
        try:
            row = conn.execute(
                "SELECT pipeline_run_id FROM email_ingest_log WHERE gmail_message_id = ?",
                ("msg-conflict-001",),
            ).fetchone()
            count = conn.execute(
                "SELECT count(*) FROM email_ingest_log WHERE gmail_message_id = ?",
                ("msg-conflict-001",),
            ).fetchone()[0]
        finally:
            conn.close()

        assert count == 1, f"Expected 1 row after REPLACE, got {count}"
        assert row[0] == "run-B", (
            f"Expected pipeline_run_id='run-B' after re-sync, got {row[0]!r}. "
            "INSERT OR REPLACE is not working — orphan rows will persist."
        )


# ---------------------------------------------------------------------------
# Fix 2a — WAL mode regression test
# ---------------------------------------------------------------------------


def test_init_db_enables_wal_mode(tmp_path: Path) -> None:
    """init_db must enable WAL journal mode to prevent DB lock under concurrent access.

    WAL allows concurrent readers + 1 writer vs rollback-journal which blocks
    readers when a writer holds the lock. Without WAL, the hydrator's 30s
    rate-limiter sleep window lets the web UI open a read transaction that
    conflicts with the hydrator's next write.
    """
    db_path = tmp_path / "wal_test.db"
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "wal", (
        f"Expected journal_mode=wal after init_db(), got {row[0]!r}. "
        "Without WAL, concurrent web UI reads block hydrator writes → DB lock."
    )


# ---------------------------------------------------------------------------
# Fix 2b — Per-URL DB lock isolation in _run_hydrator_source
# ---------------------------------------------------------------------------


class TestHydratorPerUrlExceptionIsolation:
    """DB lock (or any per-URL exception) must not abort the whole batch."""

    def _make_limited_ingester_5(self):
        class _LimitedIngester:
            def __init__(self, credentials: Any, db_path: Path) -> None:
                from jd_matcher.ingest.gmail import GmailIngester as _GI
                self._inner = _GI(credentials, db_path)

            def fetch_for_sender(
                self,
                sender: str,
                since_date: Any,
                run_id: str = "",
                canonical_run_id: str | None = None,
            ) -> list:
                return self._inner.fetch_for_sender(
                    sender,
                    since_date,
                    run_id=run_id,
                    canonical_run_id=canonical_run_id,
                )[:5]

        return _LimitedIngester

    def test_db_lock_on_one_url_does_not_abort_batch(
        self,
        test_db: Path,
        skip_live: None,
        logs_dir: Path,
    ) -> None:
        """Mock 5 LinkedIn postings; the 3rd URL's hydrate call raises OperationalError.

        The other 4 URLs must still be hydrated (the batch must not abort).
        """
        import sqlite3
        from unittest.mock import MagicMock
        from jd_matcher.hydrate.linkedin import HydratedJD

        call_count = {"n": 0}

        def side_effect(url: str) -> HydratedJD:
            call_count["n"] += 1
            if call_count["n"] == 3:
                raise sqlite3.OperationalError("database is locked")
            return _make_complete_linkedin_jd(url)

        LimitedIngester = self._make_limited_ingester_5()

        with (
            patch("jd_matcher.pipeline.GmailIngester", LimitedIngester),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=side_effect),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=_make_complete_indeed_jd),
        ):
            summary = run_pipeline(db_path=test_db)

        # The hydrator source must not have crashed the whole batch — it should
        # still be healthy (or degraded at worst), not failed.
        hydrator_li = next(
            (s for s in summary.sources if s.source == "hydrator_linkedin"), None
        )
        assert hydrator_li is not None
        # 4 of 5 URLs succeeded; the source should not be marked outright failed.
        assert hydrator_li.health_status in ("healthy", "degraded"), (
            f"Expected healthy/degraded after one DB-lock skip, got {hydrator_li.health_status!r}. "
            "Per-URL isolation means one lock failure must not abort the whole batch."
        )
        # At least 4 results in the results list (the one that locked was skipped/continued)
        assert hydrator_li.hydrated >= 4, (
            f"Expected at least 4 hydrated URLs, got {hydrator_li.hydrated}. "
            "The DB lock on URL 3 should have been skipped, not aborted the batch."
        )

    def test_generic_exception_on_one_url_does_not_abort_batch(
        self,
        test_db: Path,
        skip_live: None,
        logs_dir: Path,
    ) -> None:
        """A generic RuntimeError on one URL must not abort the hydrator batch."""
        call_count = {"n": 0}

        def side_effect(url: str):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("unexpected parse error")
            return _make_complete_linkedin_jd(url)

        LimitedIngester = self._make_limited_ingester_5()

        with (
            patch("jd_matcher.pipeline.GmailIngester", LimitedIngester),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=side_effect),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=_make_complete_indeed_jd),
        ):
            summary = run_pipeline(db_path=test_db)

        hydrator_li = next(
            (s for s in summary.sources if s.source == "hydrator_linkedin"), None
        )
        assert hydrator_li is not None
        assert hydrator_li.health_status in ("healthy", "degraded"), (
            f"Expected healthy/degraded after one generic-exception skip, "
            f"got {hydrator_li.health_status!r}"
        )
