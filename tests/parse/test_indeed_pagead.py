"""
Tests for indeed_pagead.resolve_pagead_urls (C4 sub-step, TASK-M1-005b).

All offline tests mock at the requests.Session.get boundary via the
`responses` library. The live integration test (AC #8) is guarded by
@pytest.mark.skipif(SKIP_LIVE) so it never runs in normal CI.
"""

from __future__ import annotations

import email as _email_module
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import responses as responses_lib

from jd_matcher.parse.indeed_pagead import resolve_pagead_urls

_REAL_FIXTURES_ROOT = Path(__file__).parent.parent / "fixtures" / "real"

# A syntactically valid pagead URL (html-entity form used in email HTML).
_PAGEAD_HTML = (
    "https://ca.indeed.com/pagead/clk/dl?mo=r&amp;ad=-6NYlbfkN0BVuNm4F_ixI_"
    "CC9wvjvkRqrqX9krstMh&amp;tk=1iqabcd1234567abc"
)
# Unescaped form (after html.unescape).
_PAGEAD_PLAIN = (
    "https://ca.indeed.com/pagead/clk/dl?mo=r&ad=-6NYlbfkN0BVuNm4F_ixI_"
    "CC9wvjvkRqrqX9krstMh&tk=1iqabcd1234567abc"
)
# The redirect destination that Indeed returns.
_VIEWJOB_WITH_TRACKING = (
    "https://ca.indeed.com/viewjob?jk=abcdef1234567890&q=data+scientist&l=Vancouver"
    "&from=jaopv3&tk=1iqabcd1234567abc"
)
_CANONICAL = "https://ca.indeed.com/viewjob?jk=abcdef1234567890"

_NON_PAGEAD = "https://ca.indeed.com/rc/clk?jk=aabb1234567890cc"


# ---------------------------------------------------------------------------
# AC #1 — Idempotent: non-pagead URLs pass through unchanged
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_non_pagead_urls_pass_through_unchanged() -> None:
    """URLs without 'pagead/clk' are returned as-is without any HTTP call."""
    result = resolve_pagead_urls([_NON_PAGEAD])
    assert result == {_NON_PAGEAD: _NON_PAGEAD}
    assert len(responses_lib.calls) == 0, "No HTTP call should be made for non-pagead URLs"


@responses_lib.activate
def test_mixed_pagead_and_non_pagead() -> None:
    """Non-pagead entries pass through; only pagead entries get HTTP calls."""
    responses_lib.add(
        responses_lib.GET,
        _PAGEAD_PLAIN,
        status=200,
        headers={"Location": _VIEWJOB_WITH_TRACKING},
        match_querystring=False,
    )
    result = resolve_pagead_urls([_PAGEAD_PLAIN, _NON_PAGEAD])
    assert result[_NON_PAGEAD] == _NON_PAGEAD
    assert len(responses_lib.calls) == 1


# ---------------------------------------------------------------------------
# AC #2 — html.unescape() applied before the HTTP request
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_html_entities_unescaped_before_fetch() -> None:
    """URL with &amp; entities is unescaped before the HTTP GET is made."""
    # Register the UNESCAPED URL — if html.unescape() is skipped the mock
    # won't match and the call will raise ConnectionError.
    responses_lib.add(
        responses_lib.GET,
        _PAGEAD_PLAIN,
        status=200,
        body=b"",
        headers={"Location": _VIEWJOB_WITH_TRACKING},
        match_querystring=False,
    )
    # Pass the HTML-entity form (as it appears in email HTML).
    result = resolve_pagead_urls([_PAGEAD_HTML])
    assert len(responses_lib.calls) == 1
    # The URL actually fetched must be the unescaped form.
    fetched = responses_lib.calls[0].request.url
    assert "&amp;" not in fetched, f"html.unescape() was not applied: {fetched}"


# ---------------------------------------------------------------------------
# AC #3 — Jitter: time.sleep called with values in [3.0, 4.5] between requests
# ---------------------------------------------------------------------------

@responses_lib.activate
@patch("jd_matcher.parse.indeed_pagead.time.sleep")
def test_jitter_sleep_called_between_requests(mock_sleep) -> None:
    """time.sleep is called between consecutive requests with delay in [3.0, 4.5]."""
    pagead_a = "https://ca.indeed.com/pagead/clk/dl?mo=r&ad=AAAA"
    pagead_b = "https://ca.indeed.com/pagead/clk/dl?mo=r&ad=BBBB"
    pagead_c = "https://ca.indeed.com/pagead/clk/dl?mo=r&ad=CCCC"

    for url in (pagead_a, pagead_b, pagead_c):
        responses_lib.add(
            responses_lib.GET,
            url,
            status=200,
            body=b"",
            match_querystring=False,
        )

    resolve_pagead_urls([pagead_a, pagead_b, pagead_c])

    # 3 requests → 2 inter-request gaps → 2 sleep calls
    assert mock_sleep.call_count == 2, (
        f"Expected 2 sleep calls for 3 requests, got {mock_sleep.call_count}"
    )
    for call in mock_sleep.call_args_list:
        delay = call[0][0]
        assert 3.0 <= delay <= 4.5, f"Sleep delay {delay} outside [3.0, 4.5]"


@responses_lib.activate
@patch("jd_matcher.parse.indeed_pagead.time.sleep")
def test_no_trailing_sleep_after_last_request(mock_sleep) -> None:
    """No sleep call is issued after the final request in the batch."""
    responses_lib.add(
        responses_lib.GET,
        _PAGEAD_PLAIN,
        status=200,
        body=b"",
        match_querystring=False,
    )
    resolve_pagead_urls([_PAGEAD_PLAIN])
    assert mock_sleep.call_count == 0, "Should not sleep after a single-URL batch"


# ---------------------------------------------------------------------------
# AC #4 — Browser-mimicking headers
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_browser_headers_applied() -> None:
    """Requests include Chrome User-Agent, mail.google.com Referer, and text/html Accept."""
    responses_lib.add(
        responses_lib.GET,
        _PAGEAD_PLAIN,
        status=200,
        body=b"",
        match_querystring=False,
    )
    resolve_pagead_urls([_PAGEAD_PLAIN])
    assert len(responses_lib.calls) == 1
    req = responses_lib.calls[0].request

    ua = req.headers.get("User-Agent", "")
    assert "Chrome" in ua and "Mozilla" in ua, f"Unexpected User-Agent: {ua}"

    referer = req.headers.get("Referer", "")
    assert referer == "https://mail.google.com/", f"Unexpected Referer: {referer}"

    accept = req.headers.get("Accept", "")
    assert accept.startswith("text/html"), f"Accept does not start with text/html: {accept}"


# ---------------------------------------------------------------------------
# AC #5 — Session reuse: cookies accumulate across requests
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_session_cookies_accumulate() -> None:
    """Cookies set in the first response are sent with the second request."""
    pagead_a = "https://ca.indeed.com/pagead/clk/dl?mo=r&ad=FIRST"
    pagead_b = "https://ca.indeed.com/pagead/clk/dl?mo=r&ad=SECOND"

    # First response sets a session cookie.
    responses_lib.add(
        responses_lib.GET,
        pagead_a,
        status=200,
        body=b"",
        headers={"Set-Cookie": "__cf_bm=testcookievalue; Path=/; HttpOnly"},
        match_querystring=False,
    )
    # Second response — we'll inspect whether the cookie was sent.
    responses_lib.add(
        responses_lib.GET,
        pagead_b,
        status=200,
        body=b"",
        match_querystring=False,
    )

    import requests as _requests

    import jd_matcher.parse.indeed_pagead as _mod

    original_sleep = _mod.time.sleep
    _mod.time.sleep = lambda _: None  # skip actual sleep in this test
    try:
        resolve_pagead_urls([pagead_a, pagead_b])
    finally:
        _mod.time.sleep = original_sleep

    assert len(responses_lib.calls) == 2
    # The second request must carry the cookie set by the first response.
    second_req = responses_lib.calls[1].request
    cookie_header = second_req.headers.get("Cookie", "")
    assert "__cf_bm" in cookie_header, (
        f"Cookie from first response not forwarded to second request. Cookie header: {cookie_header!r}"
    )


# ---------------------------------------------------------------------------
# AC #6 — Tracking params stripped from canonical URL
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_tracking_params_stripped_from_canonical() -> None:
    """Resolved URL keeps only jk= — all tracking params are discarded."""
    # Simulate the redirect: pagead URL → 302 → viewjob with tracking params → 200
    responses_lib.add(
        responses_lib.GET,
        _PAGEAD_PLAIN,
        status=302,
        headers={"Location": _VIEWJOB_WITH_TRACKING},
        body=b"",
        match_querystring=False,
    )
    responses_lib.add(
        responses_lib.GET,
        _VIEWJOB_WITH_TRACKING,
        status=200,
        body=b"<html></html>",
        match_querystring=False,
    )
    result = resolve_pagead_urls([_PAGEAD_PLAIN])
    canonical = result[_PAGEAD_PLAIN]
    assert canonical == _CANONICAL, f"Expected {_CANONICAL}, got {canonical}"
    # Verify no tracking params leaked through.
    assert "q=" not in canonical
    assert "l=" not in canonical
    assert "from=" not in canonical
    assert "tk=" not in canonical


# ---------------------------------------------------------------------------
# AC #7 — Offline mode: JD_MATCHER_OFFLINE_PARSE=1 skips all resolution
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_offline_mode_skips_http(monkeypatch) -> None:
    """JD_MATCHER_OFFLINE_PARSE=1 returns all URLs unchanged without HTTP calls."""
    monkeypatch.setenv("JD_MATCHER_OFFLINE_PARSE", "1")
    urls = [_PAGEAD_PLAIN, _NON_PAGEAD]
    result = resolve_pagead_urls(urls)
    assert result == {u: u for u in urls}
    assert len(responses_lib.calls) == 0, "No HTTP calls should be made in offline mode"


# ---------------------------------------------------------------------------
# Failure handling — 4xx / connection error returns passthrough, not drop
# ---------------------------------------------------------------------------

@responses_lib.activate
@patch("jd_matcher.parse.indeed_pagead.time.sleep")
def test_failed_url_returns_passthrough_not_dropped(mock_sleep) -> None:
    """A URL that triggers a 403 is included in output as original==canonical."""
    pagead_403 = "https://ca.indeed.com/pagead/clk/dl?mo=r&ad=BLOCKED"
    responses_lib.add(
        responses_lib.GET,
        pagead_403,
        status=403,
        body=b"Forbidden",
        match_querystring=False,
    )
    result = resolve_pagead_urls([pagead_403])
    # Must be present in the result (not silently dropped).
    assert pagead_403 in result
    # Passthrough: original == canonical for the failed URL.
    assert result[pagead_403] == pagead_403


@responses_lib.activate
@patch("jd_matcher.parse.indeed_pagead.time.sleep")
def test_connection_error_returns_passthrough(mock_sleep) -> None:
    """A network error returns the original URL as a passthrough, not a crash."""
    pagead_err = "https://ca.indeed.com/pagead/clk/dl?mo=r&ad=NETERR"
    responses_lib.add(
        responses_lib.GET,
        pagead_err,
        body=ConnectionError("simulated network failure"),
        match_querystring=False,
    )
    result = resolve_pagead_urls([pagead_err])
    assert pagead_err in result
    assert result[pagead_err] == pagead_err


@responses_lib.activate
@patch("jd_matcher.parse.indeed_pagead.time.sleep")
def test_batch_continues_after_single_failure(mock_sleep) -> None:
    """A failure on URL #1 does not abort resolution of URL #2."""
    pagead_fail = "https://ca.indeed.com/pagead/clk/dl?mo=r&ad=FAIL"
    pagead_ok = "https://ca.indeed.com/pagead/clk/dl?mo=r&ad=OK"

    responses_lib.add(
        responses_lib.GET,
        pagead_fail,
        status=500,
        body=b"Server Error",
        match_querystring=False,
    )
    responses_lib.add(
        responses_lib.GET,
        pagead_ok,
        status=302,
        headers={"Location": "https://ca.indeed.com/viewjob?jk=1234567890abcdef"},
        body=b"",
        match_querystring=False,
    )
    responses_lib.add(
        responses_lib.GET,
        "https://ca.indeed.com/viewjob?jk=1234567890abcdef",
        status=200,
        body=b"<html></html>",
        match_querystring=False,
    )

    result = resolve_pagead_urls([pagead_fail, pagead_ok])
    assert pagead_fail in result
    assert pagead_ok in result
    assert result[pagead_ok] == "https://ca.indeed.com/viewjob?jk=1234567890abcdef"


# ---------------------------------------------------------------------------
# AC #9 hint — sleep call count implies ≤75s for 15 URLs
# ---------------------------------------------------------------------------

@responses_lib.activate
@patch("jd_matcher.parse.indeed_pagead.time.sleep")
def test_15_url_batch_sleep_call_count(mock_sleep) -> None:
    """15-URL batch produces exactly 14 sleep calls (15 - 1 inter-request gaps)."""
    urls = [
        f"https://ca.indeed.com/pagead/clk/dl?mo=r&ad=BATCH{i:02d}"
        for i in range(15)
    ]
    for url in urls:
        responses_lib.add(
            responses_lib.GET,
            url,
            status=200,
            body=b"",
            match_querystring=False,
        )
    resolve_pagead_urls(urls)
    # 14 inter-request gaps × max 4.5s each = 63s < 75s ceiling.
    assert mock_sleep.call_count == 14


# ---------------------------------------------------------------------------
# AC #8 — Real-data integration test (requires live Indeed HTTP)
# ---------------------------------------------------------------------------

_INDEED_REAL_FILES = [
    "1 new Data Science opportunity in Vancouver, BC.eml",
    "1 new Senior Data Analyst opportunity in Vancouver, BC.eml",
    "French Canada - AI Data Contributor at Acolad and 12 more Machine Learning Engineer jobs in Canada for you!.eml",
    "Head of Growth and Performance Marketing (426) at Trail Appliances Ltd. and 8 more Machine Learning Engineer jobs in Vancouver, BC for you!.eml",
    "Software Engineer, iOS Core Product - Waterloo, Canada at Speechify and 5 more AI Engineer jobs in Canada for you!.eml",
    "Stantec is hiring for Junior Environmental Scientist or EIT + 4 new Research Scientist jobs in Vancouver, BC.eml",
]

# Claimed job counts from email subjects (lower bound; used for extraction-rate check).
_SUBJECT_CLAIMS = {
    "1 new Data Science opportunity in Vancouver, BC.eml": 1,
    "1 new Senior Data Analyst opportunity in Vancouver, BC.eml": 1,
    "French Canada - AI Data Contributor at Acolad and 12 more Machine Learning Engineer jobs in Canada for you!.eml": 13,
    "Head of Growth and Performance Marketing (426) at Trail Appliances Ltd. and 8 more Machine Learning Engineer jobs in Vancouver, BC for you!.eml": 9,
    "Software Engineer, iOS Core Product - Waterloo, Canada at Speechify and 5 more AI Engineer jobs in Canada for you!.eml": 6,
    "Stantec is hiring for Junior Environmental Scientist or EIT + 4 new Research Scientist jobs in Vancouver, BC.eml": 5,
}
_TOTAL_CLAIMED = sum(_SUBJECT_CLAIMS.values())  # 35


@pytest.mark.skipif(
    os.environ.get("SKIP_LIVE") == "1",
    reason="live Indeed HTTP — skipped under SKIP_LIVE=1",
)
def test_real_data_extraction_rate_at_least_95_percent() -> None:
    """AC #8: ≥95% extraction rate against 6 real Indeed .eml fixtures.

    Reads all 6 files, parses them through the full Indeed pipeline
    (including pagead resolution over real HTTP), and asserts that
    extracted job count ≥ 95% of subject-claimed jobs.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

    from email.header import decode_header, make_header
    from email.utils import parsedate_to_datetime

    from jd_matcher.ingest.gmail import RawEmail
    from jd_matcher.parse.indeed_email import parse

    total_extracted = 0

    for filename in _INDEED_REAL_FILES:
        eml_path = _REAL_FIXTURES_ROOT / filename
        body_bytes = eml_path.read_bytes()
        msg = _email_module.message_from_bytes(body_bytes)

        def dh(raw: str) -> str:
            try:
                return str(make_header(decode_header(raw)))
            except Exception:
                return raw

        try:
            received_at = parsedate_to_datetime(msg.get("Date", "")).astimezone(timezone.utc)
        except Exception:
            received_at = datetime.now(timezone.utc)

        raw = RawEmail(
            id=eml_path.stem,
            sender=dh(msg.get("From", "")),
            subject=dh(msg.get("Subject", "")),
            received_at=received_at,
            body_bytes=body_bytes,
        )
        postings = parse(raw)
        total_extracted += len(postings)

    extraction_rate = total_extracted / _TOTAL_CLAIMED
    assert extraction_rate >= 0.95, (
        f"Extraction rate {extraction_rate:.1%} below 95% threshold "
        f"({total_extracted}/{_TOTAL_CLAIMED} jobs extracted)"
    )
