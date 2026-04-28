"""Unit tests for browser_fetcher.py.

All tests mock patchright primitives — no live browser launches.
Tests cover both tiers and the two-tier orchestration in fetch_html().
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REAL_HTML = "<html><body>Real JD content</body></html>"
_CF_HTML_TITLE = "<html><head><title>Security Check</title></head><body></body></html>"
_CF_HTML_MOMENT = "<html><body>Just a moment...</body></html>"
_CF_HTML_RAY = "<html><body>Cloudflare Ray ID: abc123def</body></html>"


def _make_page(content: str = _REAL_HTML, status: int = 200) -> MagicMock:
    page = MagicMock()
    resp = MagicMock()
    resp.status = status
    page.goto.return_value = resp
    page.content.return_value = content
    return page


def _make_ctx(page: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.new_page.return_value = page
    return ctx


# ---------------------------------------------------------------------------
# Tier 1 tests
# ---------------------------------------------------------------------------


@patch("jd_matcher.hydrate.browser_fetcher._get_persistent_context")
def test_fetch_html_tier1_success(mock_get_ctx: MagicMock) -> None:
    """Tier 1 returns HTML bytes and 'patchright' label on clean page."""
    page = _make_page(_REAL_HTML, status=200)
    mock_get_ctx.return_value = _make_ctx(page)

    from jd_matcher.hydrate.browser_fetcher import fetch_html

    html, source = fetch_html("https://example.com/job")

    assert source == "patchright"
    assert html is not None
    assert b"Real JD content" in html
    page.close.assert_called_once()


@patch("jd_matcher.hydrate.browser_fetcher._get_persistent_context")
def test_fetch_html_tier1_cf_title_escalates(mock_get_ctx: MagicMock) -> None:
    """When Tier 1 sees a 'Security Check' page, it returns None (escalation signal)."""
    page = _make_page(_CF_HTML_TITLE, status=200)
    mock_get_ctx.return_value = _make_ctx(page)

    from jd_matcher.hydrate.browser_fetcher import _fetch_via_patchright

    result = _fetch_via_patchright("https://example.com/job", timeout=30)
    assert result is None
    page.close.assert_called_once()


@patch("jd_matcher.hydrate.browser_fetcher._get_persistent_context")
def test_fetch_html_tier1_cf_moment_escalates(mock_get_ctx: MagicMock) -> None:
    """'Just a moment' page is also recognized as a CF challenge."""
    page = _make_page(_CF_HTML_MOMENT, status=200)
    mock_get_ctx.return_value = _make_ctx(page)

    from jd_matcher.hydrate.browser_fetcher import _fetch_via_patchright

    result = _fetch_via_patchright("https://example.com/job", timeout=30)
    assert result is None


@patch("jd_matcher.hydrate.browser_fetcher._get_persistent_context")
def test_fetch_html_tier1_cf_ray_id_escalates(mock_get_ctx: MagicMock) -> None:
    """'Cloudflare Ray ID:' in body is recognized as a CF challenge."""
    page = _make_page(_CF_HTML_RAY, status=200)
    mock_get_ctx.return_value = _make_ctx(page)

    from jd_matcher.hydrate.browser_fetcher import _fetch_via_patchright

    result = _fetch_via_patchright("https://example.com/job", timeout=30)
    assert result is None


@patch("jd_matcher.hydrate.browser_fetcher._get_persistent_context")
def test_fetch_html_tier1_http_400_returns_none(mock_get_ctx: MagicMock) -> None:
    """HTTP 4xx from Tier 1 returns None without raising."""
    page = _make_page(_REAL_HTML, status=403)
    mock_get_ctx.return_value = _make_ctx(page)

    from jd_matcher.hydrate.browser_fetcher import _fetch_via_patchright

    result = _fetch_via_patchright("https://example.com/job", timeout=30)
    assert result is None
    page.close.assert_called_once()


@patch("jd_matcher.hydrate.browser_fetcher._get_persistent_context")
def test_fetch_html_tier1_goto_none_returns_none(mock_get_ctx: MagicMock) -> None:
    """When page.goto returns None (navigation failed), Tier 1 returns None."""
    page = MagicMock()
    page.goto.return_value = None
    mock_get_ctx.return_value = _make_ctx(page)

    from jd_matcher.hydrate.browser_fetcher import _fetch_via_patchright

    result = _fetch_via_patchright("https://example.com/job", timeout=30)
    assert result is None
    page.close.assert_called_once()


@patch("jd_matcher.hydrate.browser_fetcher._get_persistent_context")
def test_fetch_html_tier1_exception_returns_none(mock_get_ctx: MagicMock) -> None:
    """Exception in Tier 1 (e.g. timeout) is caught and returns None."""
    page = MagicMock()
    page.goto.side_effect = Exception("TimeoutError: page timed out")
    mock_get_ctx.return_value = _make_ctx(page)

    from jd_matcher.hydrate.browser_fetcher import _fetch_via_patchright

    result = _fetch_via_patchright("https://example.com/job", timeout=30)
    assert result is None
    page.close.assert_called_once()


# ---------------------------------------------------------------------------
# Tier 2 CDP tests
# ---------------------------------------------------------------------------


@patch("jd_matcher.hydrate.browser_fetcher._is_cdp_chrome_available", return_value=False)
def test_fetch_via_cdp_unavailable_returns_none(mock_cdp: MagicMock) -> None:
    """When CDP port is not open, _fetch_via_cdp returns None immediately."""
    from jd_matcher.hydrate.browser_fetcher import _fetch_via_cdp

    result = _fetch_via_cdp("https://example.com/job", timeout=30)
    assert result is None


@patch("jd_matcher.hydrate.browser_fetcher._is_cdp_chrome_available", return_value=True)
@patch("jd_matcher.hydrate.browser_fetcher.sync_playwright")
def test_fetch_via_cdp_success(mock_spw: MagicMock, mock_cdp: MagicMock) -> None:
    """Tier 2 returns HTML bytes when CDP is available and page loads cleanly."""
    page = MagicMock()
    resp = MagicMock()
    resp.status = 200
    page.goto.return_value = resp
    page.content.return_value = _REAL_HTML

    ctx = MagicMock()
    ctx.new_page.return_value = page

    browser = MagicMock()
    browser.contexts = [ctx]

    pw_instance = MagicMock()
    pw_instance.__enter__ = MagicMock(return_value=pw_instance)
    pw_instance.__exit__ = MagicMock(return_value=False)
    pw_instance.chromium.connect_over_cdp.return_value = browser
    mock_spw.return_value.start.return_value = pw_instance

    from jd_matcher.hydrate.browser_fetcher import _fetch_via_cdp

    result = _fetch_via_cdp("https://example.com/job", timeout=30)
    assert result is not None
    assert b"Real JD content" in result
    page.close.assert_called_once()


@patch("jd_matcher.hydrate.browser_fetcher._is_cdp_chrome_available", return_value=True)
@patch("jd_matcher.hydrate.browser_fetcher.sync_playwright")
def test_fetch_via_cdp_still_cf_challenge(mock_spw: MagicMock, mock_cdp: MagicMock) -> None:
    """Tier 2 returns None if page still shows CF challenge after CDP attach."""
    page = MagicMock()
    resp = MagicMock()
    resp.status = 200
    page.goto.return_value = resp
    page.content.return_value = _CF_HTML_TITLE

    ctx = MagicMock()
    ctx.new_page.return_value = page

    browser = MagicMock()
    browser.contexts = [ctx]

    pw_instance = MagicMock()
    pw_instance.chromium.connect_over_cdp.return_value = browser
    mock_spw.return_value.start.return_value = pw_instance

    from jd_matcher.hydrate.browser_fetcher import _fetch_via_cdp

    result = _fetch_via_cdp("https://example.com/job", timeout=30)
    assert result is None


# ---------------------------------------------------------------------------
# Two-tier orchestration (fetch_html)
# ---------------------------------------------------------------------------


@patch("jd_matcher.hydrate.browser_fetcher._get_persistent_context")
@patch("jd_matcher.hydrate.browser_fetcher._is_cdp_chrome_available", return_value=False)
def test_fetch_html_tier1_cf_challenge_tier2_unavailable(
    mock_cdp: MagicMock, mock_get_ctx: MagicMock
) -> None:
    """When Tier 1 gets CF challenge and Tier 2 is unavailable: None + 'failed_all_tiers'."""
    page = _make_page(_CF_HTML_TITLE, status=200)
    mock_get_ctx.return_value = _make_ctx(page)

    from jd_matcher.hydrate.browser_fetcher import fetch_html

    html, source = fetch_html("https://example.com/job")
    assert html is None
    assert source == "failed_all_tiers"


@patch("jd_matcher.hydrate.browser_fetcher._fetch_via_patchright", return_value=None)
@patch("jd_matcher.hydrate.browser_fetcher._fetch_via_cdp")
def test_fetch_html_tier1_fails_tier2_succeeds(
    mock_cdp: MagicMock, mock_t1: MagicMock
) -> None:
    """When Tier 1 fails, Tier 2 result is used with 'cdp_attached' label."""
    mock_cdp.return_value = b"<html>CDP result</html>"

    from jd_matcher.hydrate.browser_fetcher import fetch_html

    html, source = fetch_html("https://example.com/job")
    assert source == "cdp_attached"
    assert html == b"<html>CDP result</html>"


@patch("jd_matcher.hydrate.browser_fetcher._fetch_via_patchright")
@patch("jd_matcher.hydrate.browser_fetcher._fetch_via_cdp", return_value=None)
def test_fetch_html_tier1_succeeds_tier2_not_called(
    mock_cdp: MagicMock, mock_t1: MagicMock
) -> None:
    """When Tier 1 succeeds, Tier 2 is never called."""
    mock_t1.return_value = b"<html>Patchright result</html>"

    from jd_matcher.hydrate.browser_fetcher import fetch_html

    html, source = fetch_html("https://example.com/job")
    assert source == "patchright"
    assert html == b"<html>Patchright result</html>"
    mock_cdp.assert_not_called()
