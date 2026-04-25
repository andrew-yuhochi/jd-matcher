"""
Tests for indeed_email.parse (C4 — Indeed sub-parser).

All tests use synthetic .eml fixtures under tests/fixtures/gmail/indeed/.
"""

from __future__ import annotations

import email as _email_module
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jd_matcher.ingest.gmail import RawEmail
from jd_matcher.parse.indeed_email import parse

_FIXTURES_ROOT = (
    Path(__file__).parent.parent / "fixtures" / "gmail" / "indeed"
)

# Per-fixture expected posting counts (unique canonical job keys after dedup).
# sample-001: 3 (abc... hex-prefix, HTML fallback used)
# sample-002: 2
# sample-003: 6 (ghi... non-hex prefix, plain-text works)
# sample-004: 2 (rc/clk redirect, jkl prefix, non-hex)
# sample-005: 2
# sample-006: 2 (rt.indeed.com + rc/clk, both have jk=)
# sample-007: 5
# sample-008: 1 (same jk= appears twice → dedup)
# sample-009: 2 (HTML-only)
# sample-010: 3 (salary edge case, no issues expected)
_FIXTURE_EXPECTED = {
    "sample-001.eml": 3,
    "sample-002.eml": 2,
    "sample-003.eml": 6,
    "sample-004.eml": 2,
    "sample-005.eml": 1,
    "sample-006.eml": 2,
    "sample-007.eml": 5,
    "sample-008.eml": 1,
    "sample-009.eml": 2,
    "sample-010.eml": 3,
}

_EXPECTED_TOTAL = sum(_FIXTURE_EXPECTED.values())  # 27


def _load_raw_email(filename: str) -> RawEmail:
    path = _FIXTURES_ROOT / filename
    body_bytes = path.read_bytes()
    msg = _email_module.message_from_bytes(body_bytes)
    from email.header import decode_header, make_header
    from email.utils import parsedate_to_datetime

    def dh(raw: str) -> str:
        try:
            return str(make_header(decode_header(raw)))
        except Exception:
            return raw

    sender = dh(msg.get("From", ""))
    subject = dh(msg.get("Subject", ""))
    try:
        received_at = parsedate_to_datetime(msg.get("Date", "")).astimezone(timezone.utc)
    except Exception:
        received_at = datetime.now(timezone.utc)

    return RawEmail(
        id=path.stem,
        sender=sender,
        subject=subject,
        received_at=received_at,
        body_bytes=body_bytes,
    )


@pytest.mark.parametrize("filename,expected_count", list(_FIXTURE_EXPECTED.items()))
def test_extracts_url_from_each_of_10_fixtures(filename: str, expected_count: int) -> None:
    """Every fixture yields at least 1 ParsedPosting (100% URL extraction AC)."""
    raw = _load_raw_email(filename)
    postings = parse(raw)
    assert len(postings) >= 1, f"{filename}: expected ≥1 posting, got 0"
    assert len(postings) == expected_count, (
        f"{filename}: expected {expected_count} postings, got {len(postings)}"
    )


def test_extracts_total_postings_across_all_fixtures() -> None:
    """Total posting count across 10 Indeed fixtures matches expected."""
    total = 0
    for filename in _FIXTURE_EXPECTED:
        raw = _load_raw_email(filename)
        total += len(parse(raw))
    assert total == _EXPECTED_TOTAL, f"Expected {_EXPECTED_TOTAL} total, got {total}"


def test_canonical_url_format() -> None:
    """Canonical URL follows https://ca.indeed.com/viewjob?jk={key} pattern."""
    raw = _load_raw_email("sample-001.eml")
    postings = parse(raw)
    for p in postings:
        assert p.url.startswith("https://ca.indeed.com/viewjob?jk="), (
            f"Unexpected canonical URL: {p.url}"
        )


def test_indeed_redirect_url_pattern() -> None:
    """sample-006 has rt.indeed.com redirect URLs; job IDs still extracted."""
    raw = _load_raw_email("sample-006.eml")
    postings = parse(raw)
    assert len(postings) == 2
    job_ids = {p.job_id for p in postings}
    assert "rt1234567890001" in job_ids
    assert "rt1234567890002" in job_ids


def test_indeed_jk_param_extraction() -> None:
    """Canonical URL contains the jk param as the sole query parameter."""
    raw = _load_raw_email("sample-001.eml")
    postings = parse(raw)
    for p in postings:
        assert "jk=" in p.url
        # canonical has exactly jk=<jobId> and no other tracking params
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(p.url).query)
        assert "jk" in qs
        assert qs["jk"][0] == p.job_id


def test_within_email_dedup() -> None:
    """sample-008 has same jk= URL twice; parser returns only 1 posting."""
    raw = _load_raw_email("sample-008.eml")
    postings = parse(raw)
    assert len(postings) == 1, f"Expected 1 posting after dedup, got {len(postings)}"
    assert postings[0].job_id == "dup0001234567001"


def test_html_only_body_falls_back_to_html() -> None:
    """sample-009 has no text/plain part; parser extracts URLs from HTML."""
    raw = _load_raw_email("sample-009.eml")
    postings = parse(raw)
    assert len(postings) >= 1, "HTML-only Indeed fixture yielded no postings"
    job_ids = {p.job_id for p in postings}
    assert "html9001234567001" in job_ids
    assert "html9001234567002" in job_ids


def test_salary_edge_case_does_not_crash() -> None:
    """sample-010 has salary ranges in snippets; parser handles gracefully."""
    raw = _load_raw_email("sample-010.eml")
    postings = parse(raw)
    assert len(postings) == 3, f"Expected 3 postings, got {len(postings)}"
    # salary fields are not extracted yet — should be None or absent
    for p in postings:
        assert p.url.startswith("https://ca.indeed.com/viewjob?jk=")


def test_rc_clk_redirect_pattern() -> None:
    """sample-004 uses ca.indeed.com/rc/clk redirect URLs; jk= still extracted."""
    raw = _load_raw_email("sample-004.eml")
    postings = parse(raw)
    assert len(postings) == 2
    job_ids = {p.job_id for p in postings}
    assert "jkl4567890123001" in job_ids
    assert "jkl4567890123002" in job_ids


def test_raw_body_preserved() -> None:
    """raw_body matches original body_bytes from RawEmail."""
    raw = _load_raw_email("sample-001.eml")
    postings = parse(raw)
    for p in postings:
        assert p.raw_body == raw.body_bytes


def test_source_field_is_indeed() -> None:
    """All ParsedPostings from Indeed parser have source='indeed'."""
    raw = _load_raw_email("sample-001.eml")
    postings = parse(raw)
    for p in postings:
        assert p.source == 'indeed'


def test_multi_job_digest() -> None:
    """sample-007 (5-job digest) yields exactly 5 postings."""
    raw = _load_raw_email("sample-007.eml")
    postings = parse(raw)
    assert len(postings) == 5
