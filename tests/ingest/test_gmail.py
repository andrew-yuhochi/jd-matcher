"""
Tests for src/jd_matcher/ingest/gmail.py
"""

from __future__ import annotations

import email
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.ingest.gmail import GmailIngester, RawEmail

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures" / "gmail"

LINKEDIN_FIXTURE_DIR = FIXTURES_ROOT / "linkedin"
INDEED_FIXTURE_DIR = FIXTURES_ROOT / "indeed"

SINCE_DATE = datetime(2026, 4, 20, tzinfo=timezone.utc)


@pytest.fixture()
def test_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture()
def skip_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKIP_LIVE", "1")


# ---------------------------------------------------------------------------
# RawEmail dataclass shape
# ---------------------------------------------------------------------------


class TestRawEmailDataclass:
    def test_raw_email_dataclass_fields(self) -> None:
        msg = RawEmail(
            id="test-id-001",
            sender="LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
            subject="New jobs",
            received_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
            body_bytes=b"raw bytes",
        )
        assert msg.id == "test-id-001"
        assert "linkedin.com" in msg.sender
        assert msg.subject == "New jobs"
        assert isinstance(msg.received_at, datetime)
        assert isinstance(msg.body_bytes, bytes)


# ---------------------------------------------------------------------------
# SKIP_LIVE fixture loading
# ---------------------------------------------------------------------------


class TestFetchForSenderSkipLive:
    def test_fetch_for_sender_skip_live_reads_linkedin_fixtures(
        self, skip_live_env: None, test_db: Path
    ) -> None:
        ingester = GmailIngester(credentials=None, db_path=test_db)
        results = ingester.fetch_for_sender("linkedin", SINCE_DATE)

        assert len(results) == 10
        for msg in results:
            assert isinstance(msg, RawEmail)
            assert isinstance(msg.body_bytes, bytes)
            assert len(msg.body_bytes) > 0

    def test_fetch_for_sender_skip_live_reads_indeed_fixtures(
        self, skip_live_env: None, test_db: Path
    ) -> None:
        ingester = GmailIngester(credentials=None, db_path=test_db)
        results = ingester.fetch_for_sender("indeed", SINCE_DATE)

        assert len(results) == 10
        for msg in results:
            assert isinstance(msg, RawEmail)
            assert isinstance(msg.body_bytes, bytes)

    def test_fetch_for_sender_skip_live_linkedin_sender_header(
        self, skip_live_env: None, test_db: Path
    ) -> None:
        ingester = GmailIngester(credentials=None, db_path=test_db)
        results = ingester.fetch_for_sender("linkedin", SINCE_DATE)

        for msg in results:
            assert "linkedin.com" in msg.sender.lower(), (
                f"Expected linkedin sender, got: {msg.sender!r}"
            )

    def test_fetch_for_sender_skip_live_indeed_sender_header(
        self, skip_live_env: None, test_db: Path
    ) -> None:
        ingester = GmailIngester(credentials=None, db_path=test_db)
        results = ingester.fetch_for_sender("indeed", SINCE_DATE)

        for msg in results:
            assert "indeed.com" in msg.sender.lower(), (
                f"Expected indeed sender, got: {msg.sender!r}"
            )


# ---------------------------------------------------------------------------
# pipeline_runs — healthy path
# ---------------------------------------------------------------------------


class TestPipelineRunsHealthy:
    def test_fetch_for_sender_writes_healthy_pipeline_run_on_success(
        self, skip_live_env: None, test_db: Path
    ) -> None:
        ingester = GmailIngester(credentials=None, db_path=test_db)
        ingester.fetch_for_sender("linkedin", SINCE_DATE, run_id="test-run-healthy-001")

        conn = sqlite3.connect(test_db)
        row = conn.execute(
            "SELECT health_status, last_successful_fetch_at, failure_reason "
            "FROM pipeline_runs WHERE run_id = 'test-run-healthy-001'"
        ).fetchone()
        conn.close()

        assert row is not None
        health_status, last_successful, failure_reason = row
        assert health_status == "healthy"
        assert last_successful is not None, "last_successful_fetch_at must be populated on success"
        assert failure_reason is None

    def test_fetch_for_sender_healthy_run_source_name(
        self, skip_live_env: None, test_db: Path
    ) -> None:
        ingester = GmailIngester(credentials=None, db_path=test_db)
        ingester.fetch_for_sender("indeed", SINCE_DATE, run_id="test-run-healthy-002")

        conn = sqlite3.connect(test_db)
        row = conn.execute(
            "SELECT source FROM pipeline_runs WHERE run_id = 'test-run-healthy-002'"
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "gmail_indeed"


# ---------------------------------------------------------------------------
# pipeline_runs — failure path + non-re-raise contract
# ---------------------------------------------------------------------------


class TestPipelineRunsFailure:
    def test_fetch_for_sender_writes_failed_pipeline_run_on_exception(
        self, monkeypatch: pytest.MonkeyPatch, test_db: Path
    ) -> None:
        # Force SKIP_LIVE=1 but point fixture root to a non-existent dir so
        # _fetch_from_fixtures raises.
        monkeypatch.setenv("SKIP_LIVE", "1")

        import jd_matcher.ingest.gmail as gmail_module

        bad_root = Path("/nonexistent/fixtures/root")
        monkeypatch.setattr(gmail_module, "_FIXTURES_ROOT", bad_root)

        ingester = GmailIngester(credentials=None, db_path=test_db)
        result = ingester.fetch_for_sender("linkedin", SINCE_DATE, run_id="test-run-fail-001")

        # Must return empty list, never re-raise.
        assert result == [], "fetch_for_sender must return [] on failure, not re-raise"

        conn = sqlite3.connect(test_db)
        row = conn.execute(
            "SELECT health_status, failure_reason FROM pipeline_runs "
            "WHERE run_id = 'test-run-fail-001'"
        ).fetchone()
        conn.close()

        assert row is not None
        health_status, failure_reason = row
        assert health_status == "failed"
        assert failure_reason is not None and len(failure_reason) > 0

    def test_fetch_for_sender_oauth_token_invalid_writes_failed_run(
        self, monkeypatch: pytest.MonkeyPatch, test_db: Path
    ) -> None:
        """When live path raises OAuthTokenInvalid the run row must be failed."""
        monkeypatch.delenv("SKIP_LIVE", raising=False)

        from jd_matcher.auth.gmail_oauth import OAuthTokenInvalid
        import jd_matcher.ingest.gmail as gmail_module

        # Patch _fetch_from_gmail to raise OAuthTokenInvalid.
        def _raise_oauth(*_args: object, **_kwargs: object) -> list:
            raise OAuthTokenInvalid("oauth_token_invalid")

        monkeypatch.setattr(gmail_module.GmailIngester, "_fetch_from_gmail", _raise_oauth)

        ingester = GmailIngester(credentials=None, db_path=test_db)
        result = ingester.fetch_for_sender("linkedin", SINCE_DATE, run_id="test-run-oauth-001")

        assert result == []

        conn = sqlite3.connect(test_db)
        row = conn.execute(
            "SELECT health_status, failure_reason FROM pipeline_runs "
            "WHERE run_id = 'test-run-oauth-001'"
        ).fetchone()
        conn.close()

        assert row is not None
        health_status, failure_reason = row
        assert health_status == "failed"
        assert "oauth_token_invalid" in (failure_reason or "").lower()

    def test_last_successful_fetch_at_carried_forward_on_failure(
        self, monkeypatch: pytest.MonkeyPatch, test_db: Path
    ) -> None:
        """A prior healthy run's timestamp is carried forward on subsequent failure."""
        monkeypatch.setenv("SKIP_LIVE", "1")

        ingester = GmailIngester(credentials=None, db_path=test_db)
        # Healthy run first.
        ingester.fetch_for_sender("linkedin", SINCE_DATE, run_id="test-run-carry-healthy")

        # Now break the fixture root.
        import jd_matcher.ingest.gmail as gmail_module

        bad_root = Path("/nonexistent/fixtures/root")
        monkeypatch.setattr(gmail_module, "_FIXTURES_ROOT", bad_root)

        ingester.fetch_for_sender("linkedin", SINCE_DATE, run_id="test-run-carry-fail")

        conn = sqlite3.connect(test_db)
        rows = conn.execute(
            "SELECT health_status, last_successful_fetch_at FROM pipeline_runs "
            "WHERE run_id IN ('test-run-carry-healthy', 'test-run-carry-fail') "
            "ORDER BY id"
        ).fetchall()
        conn.close()

        healthy_row = rows[0]
        failed_row = rows[1]

        assert healthy_row[0] == "healthy"
        assert healthy_row[1] is not None

        assert failed_row[0] == "failed"
        # The failed row should carry forward the healthy run's timestamp.
        assert failed_row[1] == healthy_row[1], (
            "Failed run must carry forward last_successful_fetch_at from prior healthy run"
        )


# ---------------------------------------------------------------------------
# Fixture file structure validation
# ---------------------------------------------------------------------------


class TestFixtureStructure:
    @pytest.mark.parametrize(
        "fixture_path",
        sorted(LINKEDIN_FIXTURE_DIR.glob("*.eml")),
        ids=lambda p: p.name,
    )
    def test_linkedin_fixtures_have_required_mime_structure(self, fixture_path: Path) -> None:
        body_bytes = fixture_path.read_bytes()
        msg = email.message_from_bytes(body_bytes)

        assert "linkedin.com" in (msg.get("From") or "").lower(), (
            f"{fixture_path.name}: expected LinkedIn From header, got {msg.get('From')!r}"
        )

        content_types = [part.get_content_type() for part in msg.walk()]
        # HTML-only fixtures (e.g. sample-010) are valid edge-case fixtures
        # for parser fallback testing — they need not be multipart.
        has_html = "text/html" in content_types
        has_plain = "text/plain" in content_types
        assert has_html or has_plain, (
            f"{fixture_path.name}: must have at least text/plain or text/html"
        )

    @pytest.mark.parametrize(
        "fixture_path",
        sorted(INDEED_FIXTURE_DIR.glob("*.eml")),
        ids=lambda p: p.name,
    )
    def test_indeed_fixtures_have_required_mime_structure(self, fixture_path: Path) -> None:
        body_bytes = fixture_path.read_bytes()
        msg = email.message_from_bytes(body_bytes)

        assert "indeed.com" in (msg.get("From") or "").lower(), (
            f"{fixture_path.name}: expected Indeed From header, got {msg.get('From')!r}"
        )

        content_types = [part.get_content_type() for part in msg.walk()]
        # HTML-only fixtures (e.g. sample-009) are valid edge-case fixtures
        # for parser fallback testing — they need not be multipart.
        has_html = "text/html" in content_types
        has_plain = "text/plain" in content_types
        assert has_html or has_plain, (
            f"{fixture_path.name}: must have at least text/plain or text/html"
        )


class TestFixtureUrlPatterns:
    _LINKEDIN_URL_RE = re.compile(r"linkedin\.com/(comm/)?jobs/view/\d+")
    _INDEED_URL_RE = re.compile(r"indeed\.com/(?:viewjob|rc/clk)\?jk=[a-z0-9]+")

    def _extract_plain_text(self, body_bytes: bytes) -> str:
        msg = email.message_from_bytes(body_bytes)
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                return payload.decode("utf-8", errors="replace") if payload else ""
        return ""

    @pytest.mark.parametrize(
        "fixture_path",
        sorted(LINKEDIN_FIXTURE_DIR.glob("*.eml")),
        ids=lambda p: p.name,
    )
    def test_linkedin_fixtures_contain_linkedin_url(self, fixture_path: Path) -> None:
        body_bytes = fixture_path.read_bytes()
        plain = self._extract_plain_text(body_bytes)
        # Also check raw bytes for quoted-printable split lines.
        raw_text = body_bytes.decode("utf-8", errors="replace")

        found_in_plain = bool(self._LINKEDIN_URL_RE.search(plain))
        # For QP-encoded fixtures the URL may be split; check raw bytes too.
        found_in_raw = bool(self._LINKEDIN_URL_RE.search(raw_text))

        assert found_in_plain or found_in_raw, (
            f"{fixture_path.name}: no linkedin.com/jobs/view/<id> URL found"
        )

    @pytest.mark.parametrize(
        "fixture_path",
        sorted(INDEED_FIXTURE_DIR.glob("*.eml")),
        ids=lambda p: p.name,
    )
    def test_indeed_fixtures_contain_indeed_url(self, fixture_path: Path) -> None:
        body_bytes = fixture_path.read_bytes()
        plain = self._extract_plain_text(body_bytes)
        raw_text = body_bytes.decode("utf-8", errors="replace")

        found_in_plain = bool(self._INDEED_URL_RE.search(plain))
        found_in_raw = bool(self._INDEED_URL_RE.search(raw_text))

        assert found_in_plain or found_in_raw, (
            f"{fixture_path.name}: no indeed.com URL with jk= parameter found"
        )


# ---------------------------------------------------------------------------
# AC7: SKIP_LIVE=1 must never invoke googleapiclient.discovery.build
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Bug 3 regression — Indeed sender filter matches real fixture senders
# ---------------------------------------------------------------------------

_REAL_FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures" / "real"


def _indeed_sender_filter() -> str:
    """Return the Indeed sender filter string from the module under test."""
    from jd_matcher.ingest.gmail import _SENDER_FILTERS
    return _SENDER_FILTERS["indeed"]


def _filter_matches_address(gmail_query: str, email_address: str) -> bool:
    """Check whether a Gmail query of the form 'from:X' matches an address.

    Supports exact match ('from:a@b.com') and domain-suffix match ('from:@b.com').
    """
    prefix = gmail_query.removeprefix("from:")
    if prefix.startswith("@"):
        # Domain-suffix pattern — match any address ending in the domain part.
        return email_address.lower().endswith(prefix.lower())
    return email_address.lower() == prefix.lower()


@pytest.mark.skipif(
    not _REAL_FIXTURES_ROOT.exists(),
    reason="tests/fixtures/real/ not present — skipping real-sender validation",
)
class TestIndeedSenderFilterMatchesRealFixtures:
    """REGRESSION (Bug 3): Indeed sender filter must match every real Indeed .eml fixture.

    Verified against tests/fixtures/real/ — the real Indeed sender is
    donotreply@jobalert.indeed.com, NOT the old filter value alert@indeed.com.
    The loose pattern 'from:@jobalert.indeed.com' is preferred so future
    variations on that domain are also caught.
    """

    @staticmethod
    def _extract_raw_from_address(eml_path: Path) -> str | None:
        """Return the bare email address from the From: header, or None."""
        body_bytes = eml_path.read_bytes()
        msg = email.message_from_bytes(body_bytes)
        from_hdr = msg.get("From", "")
        # Extract the address inside angle brackets if present, else use the raw value.
        import re
        match = re.search(r"<([^>]+)>", from_hdr)
        if match:
            return match.group(1).strip()
        return from_hdr.strip() or None

    @staticmethod
    def _is_indeed_fixture(eml_path: Path) -> bool:
        body_bytes = eml_path.read_bytes()
        msg = email.message_from_bytes(body_bytes)
        from_hdr = (msg.get("From") or "").lower()
        return "indeed" in from_hdr

    @pytest.mark.parametrize(
        "eml_path",
        [p for p in sorted(_REAL_FIXTURES_ROOT.glob("*.eml"))],
        ids=lambda p: p.name,
    )
    def test_indeed_sender_filter_matches_real_indeed_fixtures(
        self, eml_path: Path
    ) -> None:
        if not self._is_indeed_fixture(eml_path):
            pytest.skip("Not an Indeed fixture — skipping")

        address = self._extract_raw_from_address(eml_path)
        assert address is not None, f"{eml_path.name}: could not extract From address"

        sender_filter = _indeed_sender_filter()
        assert _filter_matches_address(sender_filter, address), (
            f"{eml_path.name}: Indeed sender filter {sender_filter!r} does not match "
            f"real From address {address!r}. "
            "Update _SENDER_FILTERS['indeed'] in gmail.py."
        )


class TestSkipLiveDoesNotInvokeGmailApi:
    def test_skip_live_does_not_invoke_gmail_api(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Under SKIP_LIVE=1, fetch_for_sender must not call googleapiclient.discovery.build."""
        monkeypatch.setenv("SKIP_LIVE", "1")

        db_path = tmp_path / "test.db"
        from jd_matcher.db.init_db import init_db
        init_db(db_path)

        with mock.patch("googleapiclient.discovery.build") as mock_build:
            ingester = GmailIngester(credentials=None, db_path=db_path)
            results = ingester.fetch_for_sender("linkedin", SINCE_DATE)

            assert len(results) == 10
            mock_build.assert_not_called()
