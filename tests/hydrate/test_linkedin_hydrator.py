"""Tests for LinkedIn JD Hydrator."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jd_matcher.hydrate.linkedin import HydratedJD, hydrate
from jd_matcher.hydrate import compute_source_health

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "hydration" / "linkedin"
REAL_FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "hydration" / "real"

# ---------------------------------------------------------------------------
# Synthetic fixture parametrized tests
# ---------------------------------------------------------------------------

_FIXTURE_EXPECTATIONS: dict[str, dict] = {
    "sample-001": {
        "title": "Senior Data Scientist",
        "company": "Acme Corp",
        "location": "Vancouver",
        "description_contains": "ML models",
        "status": "complete",
    },
    "sample-002": {
        "title": "Machine Learning Engineer",
        "company": "BetaTech",
        "location": "Toronto",
        "description_contains": None,  # partial — no description
        "status": "partial",
    },
    "sample-003": {
        "title": "Applied Scientist",
        "company": "GammaCo",
        "location": "Remote, Canada",
        "description_contains": "natural language processing",
        "status": "complete",
    },
    "sample-004": {
        "title": "Data Scientist",
        "company": "DeltaAnalytics",
        "location": "Vancouver, BC",
        "description_contains": "predictive models",
        "status": "complete",
    },
    "sample-005": {
        "title": "Staff Data Scientist",
        "company": "EpsilonAI",
        "location": "Montreal, QC",
        "description_contains": "ML platform",
        "status": "complete",
    },
    "sample-006": {
        "title": "Research Scientist",
        "company": "ZetaResearch",
        "location": None,  # missing in fixture
        "description_contains": "reinforcement learning",
        "status": "complete",
    },
    "sample-007": {
        "title": "Data Science Lead",
        "company": None,
        "location": None,
        "description_contains": None,
        "status": "partial",
    },
    "sample-008": {
        "title": "Senior ML Engineer",
        "company": "EtaML",
        "location": "Calgary, AB",
        "description_contains": "production ML",
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
        # JSON-LD should win over DOM
        "title": "Principal Data Scientist",
        "company": "ThetaCorp",
        "location": "Ottawa",
        "description_contains": "JSON-LD description",
        "status": "complete",
    },
}


@pytest.mark.parametrize("fixture_name", list(_FIXTURE_EXPECTATIONS.keys()))
def test_synthetic_linkedin_fixtures(fixture_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hydrator extracts expected fields from each synthetic LinkedIn fixture."""
    monkeypatch.setenv("SKIP_LIVE", "1")
    url = f"https://linkedin.com/jobs/view/{fixture_name}"
    result = hydrate(url, fixtures_dir=FIXTURES_DIR)

    expected = _FIXTURE_EXPECTATIONS[fixture_name]

    assert result.hydration_status == expected["status"], (
        f"{fixture_name}: status {result.hydration_status!r} != {expected['status']!r}"
    )
    assert result.raw_html, f"{fixture_name}: raw_html must not be empty"

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
    """Sample-009 (sign-in wall) returns failed status with raw_html still set."""
    monkeypatch.setenv("SKIP_LIVE", "1")
    url = "https://linkedin.com/jobs/view/sample-009"
    result = hydrate(url, fixtures_dir=FIXTURES_DIR)

    assert result.hydration_status == "failed"
    assert result.failure_reason == "no_parseable_content"
    assert len(result.raw_html) > 0, "raw_html must be populated even on failure"
    assert result.title is None
    assert result.description is None


def test_skip_live_uses_fixtures_no_http_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """With SKIP_LIVE=1, no HTTP request is made."""
    monkeypatch.setenv("SKIP_LIVE", "1")
    with patch("jd_matcher.hydrate.linkedin.requests") as mock_requests:
        hydrate(
            "https://linkedin.com/jobs/view/sample-001",
            fixtures_dir=FIXTURES_DIR,
        )
        mock_requests.get.assert_not_called()


# ---------------------------------------------------------------------------
# compute_source_health thresholds
# ---------------------------------------------------------------------------

def _make_results(
    n_total: int, n_failed: int, failure_reason: str = "http_404"
) -> list[HydratedJD]:
    results = []
    for i in range(n_total):
        if i < n_failed:
            results.append(
                HydratedJD(
                    url="https://linkedin.com/jobs/view/1",
                    job_id="1",
                    title=None,
                    company=None,
                    location=None,
                    description=None,
                    posted_date=None,
                    seniority_level=None,
                    employment_type=None,
                    industries=None,
                    raw_html=b"",
                    hydration_status="failed",
                    failure_reason=failure_reason,
                )
            )
        else:
            results.append(
                HydratedJD(
                    url="https://linkedin.com/jobs/view/2",
                    job_id="2",
                    title="Title",
                    company="Co",
                    location="Van",
                    description="Desc",
                    posted_date=None,
                    seniority_level=None,
                    employment_type=None,
                    industries=None,
                    raw_html=b"<html/>",
                    hydration_status="complete",
                    failure_reason=None,
                )
            )
    return results


@pytest.mark.parametrize(
    "n_total,n_failed,expected_status,expected_reason_contains",
    [
        (10, 0, "healthy", None),
        (10, 1, "healthy", None),   # 10% < 20%
        (10, 5, "degraded", "partial_hydration_failure_rate"),  # 50%
        (10, 10, "failed", None),   # 100%
    ],
)
def test_compute_source_health_thresholds(
    n_total: int,
    n_failed: int,
    expected_status: str,
    expected_reason_contains: str | None,
) -> None:
    results = _make_results(n_total, n_failed)
    status, reason = compute_source_health(results)
    assert status == expected_status, f"n_failed={n_failed}/{n_total}: got {status}"
    if expected_reason_contains is not None:
        assert reason is not None and expected_reason_contains in reason


def test_compute_source_health_100pct_429() -> None:
    """100% 429 errors → health_status='failed', failure_reason='rate_limit'."""
    results = _make_results(5, 5, failure_reason="429_rate_limited")
    status, reason = compute_source_health(results)
    assert status == "failed"
    assert reason == "rate_limit"


def test_compute_source_health_empty() -> None:
    """Empty results → healthy (no data is not a failure)."""
    status, reason = compute_source_health([])
    assert status == "healthy"
    assert reason is None


@pytest.mark.parametrize("n_fail,n_total,expected_status", [
    (0, 10, "healthy"),   # 0%
    (1, 10, "healthy"),   # 10% — below 20%
    (2, 10, "healthy"),   # 20% — boundary exact; TDD says ">20%" so 20% stays healthy
    (3, 10, "degraded"),  # 30% — above 20%
    (5, 10, "degraded"),  # 50%
    (10, 10, "failed"),   # 100%
])
def test_compute_source_health_boundary_exact(
    n_fail: int, n_total: int, expected_status: str
) -> None:
    """Per TDD §C5: '>20% → degraded' means exactly 20% stays healthy."""
    results = _make_results(n_total, n_fail)
    status, _ = compute_source_health(results)
    assert status == expected_status, (
        f"n_fail={n_fail}/{n_total} ({n_fail/n_total:.0%}): expected {expected_status!r}, got {status!r}"
    )


def test_no_silent_drops_5_urls_3_success_2_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC7: feed 5 URLs (3 success + 2 fail), assert all 5 results return.

    Critical invariant: per-URL hydration failure must NOT drop the posting.
    Each URL gets a HydratedJD result with the appropriate hydration_status.
    """
    monkeypatch.setenv("SKIP_LIVE", "1")

    # 3 valid synthetic fixtures (sample-001..003 are clean JSON-LD or DOM-parseable)
    success_urls = [
        "https://linkedin.com/jobs/view/sample-001",
        "https://linkedin.com/jobs/view/sample-002",
        "https://linkedin.com/jobs/view/sample-003",
    ]
    # 2 fail-producing URLs: sample-009 is sign-in-wall, nonexistent has no fixture file
    fail_urls = [
        "https://linkedin.com/jobs/view/sample-009",
        "https://linkedin.com/jobs/view/sample-nonexistent-9999",
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
# Real-data sanity tests (CI-safe — skipped if no real fixtures)
# ---------------------------------------------------------------------------

def _real_fixture_paths() -> list[Path]:
    if not REAL_FIXTURES_DIR.exists():
        return []
    return [p for p in REAL_FIXTURES_DIR.glob("*.html") if p.stat().st_size > 0]


@pytest.mark.parametrize(
    "fixture_path",
    _real_fixture_paths(),
    ids=[p.stem for p in _real_fixture_paths()],
)
def test_real_linkedin_fixture_parses(
    fixture_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real-captured HTML fixtures must yield title or description (or both)."""
    monkeypatch.setenv("SKIP_LIVE", "1")
    job_id = fixture_path.stem
    url = f"https://linkedin.com/jobs/view/{job_id}"
    result = hydrate(url, fixtures_dir=fixture_path.parent)

    assert result.raw_html, f"{job_id}: raw_html is empty"
    # Either the JD was parseable or we got a known-failure
    if result.hydration_status in ("complete", "partial"):
        assert result.title is not None or result.description is not None, (
            f"{job_id}: complete/partial status but both title and description are None"
        )
