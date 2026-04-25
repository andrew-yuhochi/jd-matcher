"""Tests for Indeed JD Hydrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from jd_matcher.hydrate.indeed import HydratedIndeedJD, hydrate

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
# Real-data sanity tests (CI-safe — no-ops if no Indeed real fixtures)
# ---------------------------------------------------------------------------

def _real_fixture_paths() -> list[Path]:
    """Indeed real fixtures would be in real/ with an indeed_ prefix or similar."""
    if not REAL_FIXTURES_DIR.exists():
        return []
    return [
        p for p in REAL_FIXTURES_DIR.glob("indeed_*.html")
        if p.stat().st_size > 0
    ]


@pytest.mark.parametrize(
    "fixture_path",
    _real_fixture_paths(),
    ids=[p.stem for p in _real_fixture_paths()],
)
def test_real_indeed_fixture_parses(
    fixture_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real-captured Indeed HTML fixtures must yield title or description."""
    monkeypatch.setenv("SKIP_LIVE", "1")
    job_id = fixture_path.stem
    url = _indeed_url(job_id)
    result = hydrate(url, fixtures_dir=fixture_path.parent)

    assert result.raw_html is not None
    if result.hydration_status in ("complete", "partial"):
        assert result.title is not None or result.description is not None
