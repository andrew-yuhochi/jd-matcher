"""
Pipeline integration tests for C19 — Title-Based Interest Filter.

Tests verify that filtered postings short-circuit BEFORE register_new,
no hydration is attempted, and email_ingest_log.filter_status is set
correctly under Option-C semantics (only when ALL postings from an email
are dropped).

No live network calls; hydrator is mocked.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.filter.title_filter import FilterDecision, TitleFilters, FilterPattern
from jd_matcher.pipeline import run_pipeline
from jd_matcher.parse.linkedin_email import ParsedPosting


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_filter_integ.db"
    init_db(db_path)
    return db_path


@pytest.fixture()
def logs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    import jd_matcher.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "_LOGS_DIR", log_dir)
    return log_dir


def _seed_email_log_row(db_path: Path, gmail_message_id: str, run_id: str = "test-run") -> None:
    """Insert an email_ingest_log row as GmailIngester would normally do."""
    from jd_matcher.db.email_ingest_log import insert_email_log
    insert_email_log(
        gmail_message_id=gmail_message_id,
        source="linkedin",
        sender="jobs-noreply@linkedin.com",
        subject="New jobs for you",
        received_at=_EPOCH,
        pipeline_run_id=run_id,
        db_path=db_path,
    )


def _get_email_log_row(db_path: Path, gmail_message_id: str) -> dict | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT gmail_message_id, filter_status, filter_reason,
                   urls_extracted_count, urls_new_count
            FROM email_ingest_log
            WHERE gmail_message_id = ?
            """,
            (gmail_message_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "gmail_message_id": row[0],
            "filter_status": row[1],
            "filter_reason": row[2],
            "urls_extracted_count": row[3],
            "urls_new_count": row[4],
        }
    finally:
        conn.close()


def _count_postings(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
    finally:
        conn.close()


def _count_seen_urls(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM seen_urls").fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers to build mock emails / postings
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)

PASSABLE_POSTING = ParsedPosting(
    source="linkedin",
    url="https://www.linkedin.com/jobs/view/111111",
    raw_url="https://www.linkedin.com/jobs/view/111111",
    job_id="111111",
    title="Senior Data Scientist",
    company="Acme Corp",
    location="Vancouver, BC",
    received_at=_EPOCH,
    raw_body=b"",
    gmail_message_id="msg-mixed-001",
)

FILTERABLE_POSTING = ParsedPosting(
    source="linkedin",
    url="https://www.linkedin.com/jobs/view/999999",
    raw_url="https://www.linkedin.com/jobs/view/999999",
    job_id="999999",
    title="Director of Engineering",
    company="Acme Corp",
    location="Vancouver, BC",
    received_at=_EPOCH,
    raw_body=b"",
    gmail_message_id="msg-mixed-001",
)

ALL_FILTERED_POSTING_A = ParsedPosting(
    source="linkedin",
    url="https://www.linkedin.com/jobs/view/111001",
    raw_url="https://www.linkedin.com/jobs/view/111001",
    job_id="111001",
    title="VP of Engineering",
    company="Acme Corp",
    location="Vancouver, BC",
    received_at=_EPOCH,
    raw_body=b"",
    gmail_message_id="msg-all-filtered-001",
)

ALL_FILTERED_POSTING_B = ParsedPosting(
    source="linkedin",
    url="https://www.linkedin.com/jobs/view/111002",
    raw_url="https://www.linkedin.com/jobs/view/111002",
    job_id="111002",
    title="Head of Engineering",
    company="Acme Corp",
    location="Vancouver, BC",
    received_at=_EPOCH,
    raw_body=b"",
    gmail_message_id="msg-all-filtered-001",
)


class _MockRawEmail:
    """Minimal stand-in for RawEmail; carries id + postings list."""

    def __init__(self, id_: str, postings: list[ParsedPosting]) -> None:
        self.id = id_
        self._postings = postings


def _make_mock_ingester(emails_by_sender: dict[str, list[_MockRawEmail]]) -> type:
    """Return a mock GmailIngester class that serves pre-built email lists."""

    class _MockIngester:
        def __init__(self, credentials: Any, db_path: Path) -> None:
            pass

        def fetch_for_sender(
            self,
            sender: str,
            since_date: Any,
            run_id: str = "",
            canonical_run_id: str | None = None,
        ) -> list:
            return emails_by_sender.get(sender, [])

    return _MockIngester


def _make_mock_parser(postings_per_email: dict[str, list[ParsedPosting]]):
    """Return a mock parse function that maps raw_email.id → postings."""

    def _parser(raw_email: Any) -> list[ParsedPosting]:
        return postings_per_email.get(raw_email.id, [])

    return _parser


# ---------------------------------------------------------------------------
# Integration test 1: mixed email — 1 filterable + 1 passable posting
# ---------------------------------------------------------------------------


class TestMixedEmail:
    """Fixture email with one filterable + one passable posting.

    Expected:
    - Only the passable posting reaches register_new → 1 posting in DB
    - No seen_urls entry for the filtered posting URL
    - email_ingest_log.filter_status is NULL (not all dropped — Option C)
    - SourceResult.filtered_count == 1
    - Hydrator is not called for the filtered posting URL
    """

    def _build_setup(self) -> tuple:
        email_id = "msg-mixed-001"
        mock_email = _MockRawEmail(email_id, [PASSABLE_POSTING, FILTERABLE_POSTING])
        return email_id, mock_email

    def test_only_passable_reaches_register_new(
        self, test_db: Path, logs_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SKIP_LIVE", "1")
        email_id, mock_email = self._build_setup()

        mock_ingester = _make_mock_ingester({"linkedin": [mock_email], "indeed": []})
        mock_parser = _make_mock_parser({email_id: [PASSABLE_POSTING, FILTERABLE_POSTING]})

        with (
            patch("jd_matcher.pipeline.GmailIngester", mock_ingester),
            patch("jd_matcher.pipeline.parse_linkedin", mock_parser),
            patch("jd_matcher.pipeline.parse_indeed", _make_mock_parser({})),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=lambda *a, **kw: None),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=lambda *a, **kw: None),
        ):
            summary = run_pipeline(db_path=test_db)

        # Only the passable posting should be in postings + seen_urls
        assert _count_postings(test_db) == 1, "Only 1 posting should be created"
        assert _count_seen_urls(test_db) == 1, "Only 1 seen_url should be written"

        # Filtered URL must NOT be in seen_urls
        conn = sqlite3.connect(test_db)
        try:
            filtered_url_row = conn.execute(
                "SELECT url FROM seen_urls WHERE url = ?",
                (FILTERABLE_POSTING.url,),
            ).fetchone()
        finally:
            conn.close()
        assert filtered_url_row is None, (
            "Filtered posting URL must NOT be written to seen_urls"
        )

    def test_email_log_filter_status_null_for_partial_filter(
        self, test_db: Path, logs_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Option-C: filter_status stays NULL when some postings passed."""
        monkeypatch.setenv("SKIP_LIVE", "1")
        email_id, mock_email = self._build_setup()

        # Pre-seed the email_ingest_log row (normally written by GmailIngester)
        _seed_email_log_row(test_db, email_id)

        mock_ingester = _make_mock_ingester({"linkedin": [mock_email], "indeed": []})
        mock_parser = _make_mock_parser({email_id: [PASSABLE_POSTING, FILTERABLE_POSTING]})

        with (
            patch("jd_matcher.pipeline.GmailIngester", mock_ingester),
            patch("jd_matcher.pipeline.parse_linkedin", mock_parser),
            patch("jd_matcher.pipeline.parse_indeed", _make_mock_parser({})),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=lambda *a, **kw: None),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=lambda *a, **kw: None),
        ):
            run_pipeline(db_path=test_db)

        row = _get_email_log_row(test_db, email_id)
        assert row is not None, "email_ingest_log row must exist for the email"
        assert row["filter_status"] is None, (
            "Option-C: filter_status must be NULL for a partially-filtered email "
            f"(got {row['filter_status']!r})"
        )

    def test_filtered_count_in_source_result(
        self, test_db: Path, logs_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SourceResult.filtered_count reflects the number of filtered postings."""
        monkeypatch.setenv("SKIP_LIVE", "1")
        email_id, mock_email = self._build_setup()

        mock_ingester = _make_mock_ingester({"linkedin": [mock_email], "indeed": []})
        mock_parser = _make_mock_parser({email_id: [PASSABLE_POSTING, FILTERABLE_POSTING]})

        with (
            patch("jd_matcher.pipeline.GmailIngester", mock_ingester),
            patch("jd_matcher.pipeline.parse_linkedin", mock_parser),
            patch("jd_matcher.pipeline.parse_indeed", _make_mock_parser({})),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=lambda *a, **kw: None),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=lambda *a, **kw: None),
        ):
            summary = run_pipeline(db_path=test_db)

        gmail_linkedin = next(s for s in summary.sources if s.source == "gmail_linkedin")
        assert gmail_linkedin.filtered_count == 1, (
            f"Expected filtered_count=1, got {gmail_linkedin.filtered_count}"
        )


# ---------------------------------------------------------------------------
# Integration test 2: all-filter email — every posting dropped
# ---------------------------------------------------------------------------


class TestAllFilteredEmail:
    """Fixture email where ALL postings are dropped by the filter.

    Expected:
    - 0 postings in DB, 0 seen_urls
    - email_ingest_log.filter_status == 'filtered' (Option C — all dropped)
    - filter_reason contains matched pattern
    - SourceResult.filtered_count == 2
    """

    def _build_setup(self) -> tuple:
        email_id = "msg-all-filtered-001"
        mock_email = _MockRawEmail(email_id, [ALL_FILTERED_POSTING_A, ALL_FILTERED_POSTING_B])
        return email_id, mock_email

    def test_no_postings_created(
        self, test_db: Path, logs_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SKIP_LIVE", "1")
        email_id, mock_email = self._build_setup()

        mock_ingester = _make_mock_ingester({"linkedin": [mock_email], "indeed": []})
        mock_parser = _make_mock_parser(
            {email_id: [ALL_FILTERED_POSTING_A, ALL_FILTERED_POSTING_B]}
        )

        with (
            patch("jd_matcher.pipeline.GmailIngester", mock_ingester),
            patch("jd_matcher.pipeline.parse_linkedin", mock_parser),
            patch("jd_matcher.pipeline.parse_indeed", _make_mock_parser({})),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=lambda *a, **kw: None),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=lambda *a, **kw: None),
        ):
            run_pipeline(db_path=test_db)

        assert _count_postings(test_db) == 0, "No postings should be created for all-filtered email"
        assert _count_seen_urls(test_db) == 0, "No seen_urls should be written for all-filtered email"

    def test_filter_status_set_to_filtered(
        self, test_db: Path, logs_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Option-C: filter_status='filtered' ONLY when ALL postings were dropped."""
        monkeypatch.setenv("SKIP_LIVE", "1")
        email_id, mock_email = self._build_setup()

        # Pre-seed the email_ingest_log row (normally written by GmailIngester)
        _seed_email_log_row(test_db, email_id)

        mock_ingester = _make_mock_ingester({"linkedin": [mock_email], "indeed": []})
        mock_parser = _make_mock_parser(
            {email_id: [ALL_FILTERED_POSTING_A, ALL_FILTERED_POSTING_B]}
        )

        with (
            patch("jd_matcher.pipeline.GmailIngester", mock_ingester),
            patch("jd_matcher.pipeline.parse_linkedin", mock_parser),
            patch("jd_matcher.pipeline.parse_indeed", _make_mock_parser({})),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=lambda *a, **kw: None),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=lambda *a, **kw: None),
        ):
            run_pipeline(db_path=test_db)

        row = _get_email_log_row(test_db, email_id)
        assert row is not None, "email_ingest_log row must exist for the email"
        assert row["filter_status"] == "filtered", (
            f"Expected filter_status='filtered', got {row['filter_status']!r}"
        )
        assert row["filter_reason"] is not None, (
            "filter_reason should be populated when all postings were dropped"
        )

    def test_filtered_count_in_source_result(
        self, test_db: Path, logs_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SKIP_LIVE", "1")
        email_id, mock_email = self._build_setup()

        mock_ingester = _make_mock_ingester({"linkedin": [mock_email], "indeed": []})
        mock_parser = _make_mock_parser(
            {email_id: [ALL_FILTERED_POSTING_A, ALL_FILTERED_POSTING_B]}
        )

        with (
            patch("jd_matcher.pipeline.GmailIngester", mock_ingester),
            patch("jd_matcher.pipeline.parse_linkedin", mock_parser),
            patch("jd_matcher.pipeline.parse_indeed", _make_mock_parser({})),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=lambda *a, **kw: None),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=lambda *a, **kw: None),
        ):
            summary = run_pipeline(db_path=test_db)

        gmail_linkedin = next(s for s in summary.sources if s.source == "gmail_linkedin")
        assert gmail_linkedin.filtered_count == 2, (
            f"Expected filtered_count=2, got {gmail_linkedin.filtered_count}"
        )


# ---------------------------------------------------------------------------
# No hydration for filtered postings
# ---------------------------------------------------------------------------


class TestNoHydrationForFiltered:
    """Hydrator must not be called for filtered posting URLs."""

    def test_hydrator_not_called_for_filtered_url(
        self, test_db: Path, logs_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SKIP_LIVE", "1")

        email_id = "msg-hydration-check-001"
        mock_email = _MockRawEmail(email_id, [FILTERABLE_POSTING])

        mock_ingester = _make_mock_ingester({"linkedin": [mock_email], "indeed": []})
        mock_parser = _make_mock_parser({email_id: [FILTERABLE_POSTING]})

        hydrate_calls: list[str] = []

        def _tracking_hydrate(url: str, **kwargs: Any) -> None:
            hydrate_calls.append(url)
            return None

        with (
            patch("jd_matcher.pipeline.GmailIngester", mock_ingester),
            patch("jd_matcher.pipeline.parse_linkedin", mock_parser),
            patch("jd_matcher.pipeline.parse_indeed", _make_mock_parser({})),
            patch("jd_matcher.pipeline.linkedin_hydrate", side_effect=_tracking_hydrate),
            patch("jd_matcher.pipeline.indeed_hydrate", side_effect=_tracking_hydrate),
        ):
            run_pipeline(db_path=test_db)

        assert FILTERABLE_POSTING.url not in hydrate_calls, (
            f"Hydrator was called for filtered URL {FILTERABLE_POSTING.url!r} — "
            "filtered postings must not reach hydration"
        )
