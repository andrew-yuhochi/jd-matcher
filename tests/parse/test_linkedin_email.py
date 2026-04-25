"""
Tests for linkedin_email.parse (C4 — LinkedIn sub-parser).

All tests use synthetic .eml fixtures under tests/fixtures/gmail/linkedin/.
No live network calls; SKIP_LIVE=1 is not required for these tests since the
parser operates directly on bytes.
"""

from __future__ import annotations

import email as _email_module
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jd_matcher.ingest.gmail import RawEmail
from jd_matcher.parse.linkedin_email import ParsedPosting, parse

_FIXTURES_ROOT = (
    Path(__file__).parent.parent / "fixtures" / "gmail" / "linkedin"
)

# Per-fixture expected minimum posting count (unique canonical URLs).
# Total across all 10 fixtures: 3+7+1+2+1+2+7+1+2+2 = 28
_FIXTURE_EXPECTED = {
    "sample-001.eml": 3,
    "sample-002.eml": 7,
    "sample-003.eml": 1,
    "sample-004.eml": 2,
    "sample-005.eml": 1,
    "sample-006.eml": 2,
    "sample-007.eml": 7,
    "sample-008.eml": 1,   # within-email dedup: 2 occurrences → 1 posting
    "sample-009.eml": 2,
    "sample-010.eml": 2,
}

_EXPECTED_TOTAL = sum(_FIXTURE_EXPECTED.values())  # 28


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
    """Total posting count across 10 fixtures matches expected."""
    total = 0
    for filename in _FIXTURE_EXPECTED:
        raw = _load_raw_email(filename)
        total += len(parse(raw))
    assert total == _EXPECTED_TOTAL, f"Expected {_EXPECTED_TOTAL} total, got {total}"


def test_canonical_url_strips_tracking_params() -> None:
    """Canonical URL must not contain query string."""
    raw = _load_raw_email("sample-001.eml")
    postings = parse(raw)
    for p in postings:
        assert "?" not in p.url, f"URL still has query params: {p.url}"
        assert "trackingId" not in p.url
        assert "refId" not in p.url


def test_canonical_url_format() -> None:
    """Canonical URL follows https://linkedin.com/jobs/view/{id} pattern."""
    raw = _load_raw_email("sample-001.eml")
    postings = parse(raw)
    for p in postings:
        assert p.url.startswith("https://linkedin.com/jobs/view/"), (
            f"Unexpected canonical URL format: {p.url}"
        )
        assert p.url.split("/")[-1].isdigit(), f"Job ID not numeric in URL: {p.url}"


def test_canonical_url_handles_comm_variant() -> None:
    """Both /comm/jobs/view/{id} and /jobs/view/{id} produce the same canonical."""
    raw_comm = _load_raw_email("sample-001.eml")   # uses /comm/jobs/view/
    raw_bare = _load_raw_email("sample-009.eml")    # uses /jobs/view/ (no /comm/)

    postings_comm = {p.job_id: p.url for p in parse(raw_comm)}
    postings_bare = {p.job_id: p.url for p in parse(raw_bare)}

    # All canonicals from comm fixture must not contain /comm/
    for url in postings_comm.values():
        assert "/comm/" not in url, f"Canonical URL still has /comm/: {url}"

    # All canonicals from bare fixture must not contain /comm/ either
    for url in postings_bare.values():
        assert "/comm/" not in url, f"Canonical URL has /comm/ for bare fixture: {url}"

    # Verify bare pattern produces expected canonical form
    for job_id, url in postings_bare.items():
        assert url == f"https://linkedin.com/jobs/view/{job_id}"


def test_within_email_dedup() -> None:
    """sample-008 has same URL twice in body; parser returns only 1 posting."""
    raw = _load_raw_email("sample-008.eml")
    postings = parse(raw)
    assert len(postings) == 1, f"Expected 1 posting after dedup, got {len(postings)}"
    # The single posting should be for job 6660081
    assert postings[0].job_id == "6660081"


def test_html_only_body_falls_back_to_html() -> None:
    """sample-010 has no text/plain part; parser extracts URLs from HTML."""
    raw = _load_raw_email("sample-010.eml")
    postings = parse(raw)
    assert len(postings) >= 1, "HTML-only fixture yielded no postings"
    job_ids = {p.job_id for p in postings}
    assert "4440101" in job_ids
    assert "4440102" in job_ids


def test_quoted_printable_decoding() -> None:
    """sample-006 uses QP with = line continuations; URLs still extracted."""
    raw = _load_raw_email("sample-006.eml")
    postings = parse(raw)
    assert len(postings) == 2
    job_ids = {p.job_id for p in postings}
    assert "8880061" in job_ids
    assert "8880062" in job_ids


def test_best_effort_title_extraction() -> None:
    """Parser populates title when HTML has link text; URL-only fallback on failure."""
    raw = _load_raw_email("sample-001.eml")
    postings = parse(raw)
    # At least first posting should have a title from HTML link text
    assert postings[0].title is not None, "Expected title to be extracted from HTML"
    # URL must always be present regardless
    for p in postings:
        assert p.url, "URL must always be populated"


def test_raw_body_preserved() -> None:
    """raw_body matches the original body_bytes from RawEmail."""
    raw = _load_raw_email("sample-001.eml")
    postings = parse(raw)
    for p in postings:
        assert p.raw_body == raw.body_bytes, "raw_body must equal original body_bytes"


def test_source_field_is_linkedin() -> None:
    """All ParsedPostings from LinkedIn parser have source='linkedin'."""
    raw = _load_raw_email("sample-001.eml")
    postings = parse(raw)
    for p in postings:
        assert p.source == 'linkedin'


def test_received_at_preserved() -> None:
    """received_at matches the RawEmail's received_at."""
    raw = _load_raw_email("sample-001.eml")
    postings = parse(raw)
    for p in postings:
        assert p.received_at == raw.received_at


def test_url_only_fallback_still_inserts() -> None:
    """Posting is returned even when title/company/location are all None (URL-only)."""
    # sample-010 HTML-only has minimal structure; at minimum URL should be extracted
    raw = _load_raw_email("sample-010.eml")
    postings = parse(raw)
    assert len(postings) >= 1
    for p in postings:
        assert p.url  # URL is always the canonical identifier


def test_seven_job_digest() -> None:
    """sample-007 (7-job digest) yields exactly 7 postings."""
    raw = _load_raw_email("sample-007.eml")
    postings = parse(raw)
    assert len(postings) == 7


# ---------------------------------------------------------------------------
# Real-data sanity tests — gitignored fixtures, silently skipped if absent
# ---------------------------------------------------------------------------

_REAL_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "real"


def _real_linkedin_emls() -> list[Path]:
    """Discover real LinkedIn .eml files (gitignored — only present locally).

    Returns empty list if directory missing or no files matching LinkedIn sender.
    """
    if not _REAL_FIXTURES_DIR.exists():
        return []
    emls = []
    for path in _REAL_FIXTURES_DIR.glob("*.eml"):
        try:
            with open(path, "rb") as f:
                head = f.read(8192)  # real emails have long ARC headers; 4KB misses From:
            if b"jobalerts-noreply@linkedin.com" in head:
                emls.append(path)
        except Exception:
            continue
    return emls


@pytest.mark.parametrize("eml_path", _real_linkedin_emls(), ids=lambda p: p.name)
def test_real_linkedin_email_parses(eml_path: Path) -> None:
    """Sanity check: parser extracts ≥1 LinkedIn job URL from real alert emails.

    Skipped silently if tests/fixtures/real/ has no matching .eml files
    (gitignored — only present on local dev machines).
    """
    body_bytes = eml_path.read_bytes()
    raw_email = RawEmail(
        id=f"real-sanity-{eml_path.stem}",
        sender="jobalerts-noreply@linkedin.com",
        subject=eml_path.stem,
        received_at=datetime.now(timezone.utc),
        body_bytes=body_bytes,
    )

    postings = parse(raw_email)

    assert len(postings) >= 1, (
        f"No LinkedIn job URLs extracted from real fixture {eml_path.name}. "
        f"Synthetic fixtures may not capture real-world patterns."
    )

    for posting in postings:
        assert posting.url.startswith("https://linkedin.com/jobs/view/"), (
            f"Invalid canonical URL: {posting.url}"
        )
        assert posting.job_id.isdigit(), (
            f"Invalid job_id (must be all digits): {posting.job_id}"
        )
        assert posting.source == "linkedin"

    print(f"\n[real-data] {eml_path.name}: extracted {len(postings)} postings")


def test_real_fixtures_directory_status() -> None:
    """Informational test — reports whether real fixtures are present.

    Always passes; just surfaces the count in test output for visibility.
    """
    real_files = _real_linkedin_emls()
    print(f"\n[real-data] {len(real_files)} real LinkedIn .eml files found in tests/fixtures/real/")
    if not real_files:
        print("[real-data] (gitignored — empty on fresh checkouts; expected)")
