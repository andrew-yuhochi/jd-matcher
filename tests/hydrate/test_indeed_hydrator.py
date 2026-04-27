"""Tests for Indeed JD Hydrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from jd_matcher.hydrate.indeed import HydratedIndeedJD, _STEALTH_HEADERS, hydrate

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "hydration" / "indeed"
REAL_FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "hydration" / "real"

# ---------------------------------------------------------------------------
# Synthetic fixture parametrized tests
# ---------------------------------------------------------------------------

_FIXTURE_EXPECTATIONS: dict[str, dict] = {
    "sample-001": {
        "title": "Senior Data Scientist",
        "company": "Maple Analytics",
        "location": "Vancouver",
        "description_contains": "supply chain",
        "status": "complete",
    },
    "sample-002": {
        "title": "Machine Learning Engineer",
        "company": "Cedar AI",
        "location": "Toronto",
        "description_contains": None,
        "status": "partial",
    },
    "sample-003": {
        "title": "Data Scientist",
        "company": "Birch Systems",
        "location": "Remote, Canada",
        "description_contains": "recommendation systems",
        "status": "complete",
    },
    "sample-004": {
        "title": "Applied ML Scientist",
        "company": "Douglas Labs",
        "location": "Calgary, AB",
        "description_contains": "NLP",
        "status": "complete",
    },
    "sample-005": {
        "title": "Senior ML Researcher",
        "company": "Fir Institute",
        "location": "Montreal, QC",
        "description_contains": "generative models",
        "status": "complete",
    },
    "sample-006": {
        "title": "Data Science Manager",
        "company": "Hemlock Capital",
        "location": None,
        "description_contains": "risk models",
        "status": "complete",
    },
    "sample-007": {
        "title": "NLP Data Scientist",
        "company": None,
        "location": None,
        "description_contains": None,
        "status": "partial",
    },
    "sample-008": {
        "title": "AI Engineer",
        "company": "IronwoodAI",
        "location": "Ottawa, ON",
        "description_contains": "LLMs",
        "status": "complete",
    },
    "sample-009": {
        "title": None,
        "company": None,
        "location": None,
        "description_contains": None,
        "status": "failed",
    },
    "sample-010": {
        "title": "Principal Data Scientist",
        "company": "Juniper Corp",
        "location": "Victoria",
        "description_contains": "JSON-LD description",
        "status": "complete",
    },
}


def _indeed_url(fixture_name: str) -> str:
    """Construct a fake Indeed URL with the fixture name as the jk param."""
    return f"https://www.indeed.com/viewjob?jk={fixture_name}"


@pytest.mark.parametrize("fixture_name", list(_FIXTURE_EXPECTATIONS.keys()))
def test_synthetic_indeed_fixtures(fixture_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hydrator extracts expected fields from each synthetic Indeed fixture."""
    monkeypatch.setenv("SKIP_LIVE", "1")
    url = _indeed_url(fixture_name)
    result = hydrate(url, fixtures_dir=FIXTURES_DIR)

    expected = _FIXTURE_EXPECTATIONS[fixture_name]

    assert result.hydration_status == expected["status"], (
        f"{fixture_name}: status {result.hydration_status!r} != {expected['status']!r}"
    )
    assert result.raw_html is not None, f"{fixture_name}: raw_html must not be None"

    if expected["title"] is not None:
        assert result.title == expected["title"], (
            f"{fixture_name}: title mismatch: {result.title!r}"
        )

    if expected["company"] is not None:
        assert result.company == expected["company"], (
            f"{fixture_name}: company mismatch: {result.company!r}"
        )

    if expected["location"] is not None:
        assert result.location == expected["location"], (
            f"{fixture_name}: location mismatch: {result.location!r}"
        )

    if expected["description_contains"] is not None:
        assert result.description is not None, f"{fixture_name}: description is None"
        assert expected["description_contains"] in result.description, (
            f"{fixture_name}: description missing '{expected['description_contains']}'"
        )


def test_failed_path_no_parseable_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sample-009 (expired page) returns failed status with raw_html still set."""
    monkeypatch.setenv("SKIP_LIVE", "1")
    url = _indeed_url("sample-009")
    result = hydrate(url, fixtures_dir=FIXTURES_DIR)

    assert result.hydration_status == "failed"
    assert result.failure_reason == "no_parseable_content"
    assert len(result.raw_html) > 0
    assert result.title is None
    assert result.description is None


def test_skip_live_uses_fixtures_no_http_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """With SKIP_LIVE=1, no HTTP request is made."""
    monkeypatch.setenv("SKIP_LIVE", "1")
    with patch("jd_matcher.hydrate.indeed.requests") as mock_requests:
        hydrate(_indeed_url("sample-001"), fixtures_dir=FIXTURES_DIR)
        mock_requests.get.assert_not_called()


def test_no_silent_drops_5_urls_3_success_2_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC7: feed 5 URLs (3 success + 2 fail), assert all 5 results return.

    Critical invariant: per-URL hydration failure must NOT drop the posting.
    Each URL gets a HydratedIndeedJD result with the appropriate hydration_status.
    """
    monkeypatch.setenv("SKIP_LIVE", "1")

    # 3 valid synthetic fixtures (sample-001..003 are clean JSON-LD or DOM-parseable)
    success_urls = [
        _indeed_url("sample-001"),
        _indeed_url("sample-002"),
        _indeed_url("sample-003"),
    ]
    # 2 fail-producing URLs: sample-009 is expired/sign-in page, nonexistent has no fixture file
    fail_urls = [
        _indeed_url("sample-009"),
        "https://www.indeed.com/viewjob?jk=sample-nonexistent-9999",
    ]

    results = [hydrate(url, fixtures_dir=FIXTURES_DIR) for url in success_urls + fail_urls]

    assert len(results) == 5, f"Expected 5 results (3 success + 2 fail), got {len(results)}"

    statuses = [r.hydration_status for r in results]
    # sample-001 = complete, sample-002 = partial, sample-003 = complete
    complete_or_partial = sum(1 for s in statuses if s in ("complete", "partial"))
    assert complete_or_partial == 3, f"Expected 3 success results, got {complete_or_partial}: {statuses}"
    assert statuses.count("failed") == 2, f"Expected 2 failed, got {statuses.count('failed')}: {statuses}"

    failed_results = [r for r in results if r.hydration_status == "failed"]
    for r in failed_results:
        assert r.url is not None, "Failed result must still have url"
        assert r.raw_html is not None, "Failed result must have raw_html set (preserved, not None)"
        assert r.failure_reason is not None, "Failed result must have failure_reason"


# ---------------------------------------------------------------------------
# Fix 3 — Full M1-005b stealth stack tests
# ---------------------------------------------------------------------------

_SAMPLE_JSON_LD_HTML = b"""<!DOCTYPE html>
<html>
<head>
<script type="application/ld+json">
{
  "@context": "http://schema.org",
  "@type": "JobPosting",
  "title": "Data Governance Senior Analyst",
  "description": "<p>BCIT is hiring a Senior Analyst...</p>",
  "datePosted": "2026-04-15",
  "hiringOrganization": {"@type": "Organization", "name": "BCIT"},
  "jobLocation": {"@type": "Place", "address": {"addressLocality": "Burnaby, BC"}},
  "employmentType": "FULL_TIME"
}
</script>
</head>
<body></body>
</html>"""

_SAMPLE_DOM_ONLY_HTML = b"""<!DOCTYPE html>
<html>
<head></head>
<body>
  <div id="jobDescriptionText">
    <p>We are looking for a Python developer with 5+ years of experience.</p>
  </div>
</body>
</html>"""

_SAMPLE_NEITHER_HTML = b"""<!DOCTYPE html>
<html><head></head><body><p>Sign in to view this job.</p></body></html>"""


def _mock_response(content: bytes, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.url = "https://www.indeed.com/viewjob?jk=abc1234567890123"
    return resp


def test_stealth_headers_all_nine_items_present() -> None:
    """All 9 items of the M1-005b stealth stack must be in _STEALTH_HEADERS.

    Missing any Sec-Fetch-* header produces Cloudflare 403 on production Indeed URLs
    (confirmed empirically — incomplete stack with only User-Agent/Referer/Accept
    passed in the diagnostic spike failed 100% of URLs).
    """
    required = {
        "User-Agent",
        "Referer",
        "Accept",
        "Accept-Language",
        "Sec-Fetch-Site",
        "Sec-Fetch-Mode",
        "Sec-Fetch-Dest",
        "Sec-Fetch-User",
    }
    missing = required - set(_STEALTH_HEADERS.keys())
    assert not missing, (
        f"_STEALTH_HEADERS is missing required stealth-stack items: {missing}. "
        "All 8 header items (plus Session reuse = 9 total) are needed to bypass Cloudflare."
    )

    # Verify Sec-Fetch-* values are correct
    assert _STEALTH_HEADERS["Sec-Fetch-Site"] == "cross-site"
    assert _STEALTH_HEADERS["Sec-Fetch-Mode"] == "navigate"
    assert _STEALTH_HEADERS["Sec-Fetch-Dest"] == "document"
    assert _STEALTH_HEADERS["Sec-Fetch-User"] == "?1"
    assert "mail.google.com" in _STEALTH_HEADERS["Referer"]


def test_fetch_live_uses_session_with_stealth_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fetch_live must use a requests.Session (not bare requests.get) with stealth headers."""
    monkeypatch.delenv("SKIP_LIVE", raising=False)

    # Build a standalone MagicMock session WITHOUT spec=requests.Session because
    # during the test, requests.Session itself is already mocked — speccing against
    # a mock object raises InvalidSpecError in Python 3.11+.
    sess = MagicMock()
    sess.headers = MagicMock()
    sess.headers.update = MagicMock()
    sess.get.return_value = _mock_response(_SAMPLE_JSON_LD_HTML)
    sess.close = MagicMock()

    with (
        patch("jd_matcher.hydrate.indeed.requests.Session", return_value=sess),
        patch("jd_matcher.hydrate.indeed.HYDRATOR_RATE_LIMITER"),
    ):
        result = hydrate("https://www.indeed.com/viewjob?jk=abc1234567890123")

    # headers.update must have been called with the stealth headers dict
    sess.headers.update.assert_called_once_with(_STEALTH_HEADERS)
    # get must have been called with allow_redirects=True and timeout=30
    call_kwargs = sess.get.call_args[1] if sess.get.call_args[1] else {}
    assert call_kwargs.get("allow_redirects") is True, "allow_redirects=True required"
    assert call_kwargs.get("timeout") == 30, "timeout=30 required"
    # Session must be closed regardless of success/failure
    sess.close.assert_called_once()
    # Parsing must succeed with the mocked JSON-LD response
    assert result.title == "Data Governance Senior Analyst"
    assert result.hydration_status == "complete"


def test_json_ld_extraction_all_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON-LD extraction maps all 5 fields correctly from a sample JobPosting."""
    monkeypatch.setenv("SKIP_LIVE", "1")

    # Write a temporary fixture file and load it
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        fixture_path = Path(td) / "testjob1234.html"
        fixture_path.write_bytes(_SAMPLE_JSON_LD_HTML)
        result = hydrate(
            "https://www.indeed.com/viewjob?jk=testjob1234",
            fixtures_dir=Path(td),
        )

    assert result.title == "Data Governance Senior Analyst"
    assert result.company == "BCIT"
    assert result.location == "Burnaby, BC"
    assert result.description is not None and "BCIT is hiring" in result.description
    assert result.employment_type == "FULL_TIME"
    assert result.hydration_status == "complete"


def test_fallback_to_job_description_text_div(monkeypatch: pytest.MonkeyPatch) -> None:
    """When JSON-LD is absent, must fall back to #jobDescriptionText div."""
    monkeypatch.setenv("SKIP_LIVE", "1")

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        fixture_path = Path(td) / "domonly5678.html"
        fixture_path.write_bytes(_SAMPLE_DOM_ONLY_HTML)
        result = hydrate(
            "https://www.indeed.com/viewjob?jk=domonly5678",
            fixtures_dir=Path(td),
        )

    assert result.description is not None
    assert "Python developer" in result.description
    # title may be None since there is no title in this DOM-only fixture
    # status: description present → partial (no title) or complete (with title)
    assert result.hydration_status in ("complete", "partial")


def test_neither_json_ld_nor_dom_returns_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """When neither JSON-LD nor #jobDescriptionText is found, hydration_status='failed'."""
    monkeypatch.setenv("SKIP_LIVE", "1")

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        fixture_path = Path(td) / "expired9999.html"
        fixture_path.write_bytes(_SAMPLE_NEITHER_HTML)
        result = hydrate(
            "https://www.indeed.com/viewjob?jk=expired9999",
            fixtures_dir=Path(td),
        )

    assert result.hydration_status == "failed"
    assert result.title is None
    assert result.description is None


# ---------------------------------------------------------------------------
# Bug 1 — HTML stripping in JSON-LD description
# ---------------------------------------------------------------------------

_HTML_DESCRIPTION_FIXTURE = b"""<!DOCTYPE html>
<html>
<head>
<script type="application/ld+json">
{
  "@context": "http://schema.org",
  "@type": "JobPosting",
  "title": "Test Role",
  "description": "<p>First para.</p><ul><li>Bullet one</li><li>Bullet two</li></ul><p>Second para.</p>",
  "hiringOrganization": {"@type": "Organization", "name": "Test Corp"}
}
</script>
</head>
<body></body>
</html>"""


def test_json_ld_description_html_is_stripped_to_plain_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON-LD description HTML must be stripped; no angle-bracket tags in result."""
    import tempfile

    monkeypatch.setenv("SKIP_LIVE", "1")
    with tempfile.TemporaryDirectory() as td:
        fixture_path = Path(td) / "htmljob0001.html"
        fixture_path.write_bytes(_HTML_DESCRIPTION_FIXTURE)
        result = hydrate(
            "https://www.indeed.com/viewjob?jk=htmljob0001",
            fixtures_dir=Path(td),
        )

    assert result.description is not None
    assert "<" not in result.description, "HTML tags must be stripped from description"
    assert ">" not in result.description, "HTML tags must be stripped from description"
    assert "First para." in result.description
    assert "Second para." in result.description
    # Paragraphs must be separated by at least one newline
    first_idx = result.description.index("First para.")
    second_idx = result.description.index("Second para.")
    between = result.description[first_idx + len("First para.") : second_idx]
    assert "\n" in between, "Paragraph text must be separated by newlines"
