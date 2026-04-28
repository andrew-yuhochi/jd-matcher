"""Generic browser-based URL fetcher using patchright (Playwright fork).

Two-tier escalation:
  Tier 1: patchright headed + persistent Chrome profile.
          Patches the CDP Runtime.enable leak Cloudflare detects since Feb 2025.
  Tier 2: CDP-attach to user's existing Chrome at localhost:9222.
          Uses real cf_clearance cookie from a manually-solved challenge.

Public API: fetch_html(url, timeout) -> (bytes | None, str)

This module is a generic primitive — any hydrator can import it as a fallback
when requests-based fetching is blocked by Cloudflare or similar bot defences.
"""

from __future__ import annotations

import atexit
import logging
import socket
from pathlib import Path

logger = logging.getLogger(__name__)

_CLOUDFLARE_MARKERS = (
    "<title>Security Check",
    "Just a moment",
    "cf-challenge-running",
    "Cloudflare Ray ID:",
    "Checking your browser before accessing",
)

CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"

# Module-level singletons for the persistent patchright context.
# Reused across calls to avoid the cost of spinning up a new browser each time.
_playwright_handle = None
_persistent_context = None


def sync_playwright():
    """Thin wrapper around patchright's sync_playwright.

    Defined at module level so tests can patch
    jd_matcher.hydrate.browser_fetcher.sync_playwright without triggering a
    real patchright import during unit test collection.
    """
    from patchright.sync_api import sync_playwright as _spw

    return _spw()


def _get_persistent_context():
    global _playwright_handle, _persistent_context
    if _persistent_context is None:
        _playwright_handle = sync_playwright().start()
        user_data_dir = Path.home() / ".jd-matcher" / "chrome_profile_patchright"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        _persistent_context = _playwright_handle.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=False,
            no_viewport=True,
            args=["--start-minimized"],
        )
        logger.info(
            "browser_fetcher Tier 1: launched patchright persistent context at %s",
            user_data_dir,
        )
    return _persistent_context


def _shutdown_patchright() -> None:
    global _playwright_handle, _persistent_context
    if _persistent_context is not None:
        try:
            _persistent_context.close()
        except Exception:
            pass
        _persistent_context = None
    if _playwright_handle is not None:
        try:
            _playwright_handle.stop()
        except Exception:
            pass
        _playwright_handle = None


atexit.register(_shutdown_patchright)


def _is_cloudflare_challenge(html: str) -> bool:
    return any(marker in html for marker in _CLOUDFLARE_MARKERS)


def _fetch_via_patchright(url: str, timeout: int) -> bytes | None:
    try:
        ctx = _get_persistent_context()
    except Exception as exc:
        logger.error(
            "browser_fetcher Tier 1: failed to get persistent context: %s", exc
        )
        return None

    page = ctx.new_page()
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        if resp is None or resp.status >= 400:
            logger.warning(
                "browser_fetcher Tier 1: HTTP %s for %s",
                resp.status if resp else "None",
                url,
            )
            return None
        html = page.content()
        if _is_cloudflare_challenge(html):
            logger.warning(
                "browser_fetcher Tier 1: CF challenge detected for %s — escalating to Tier 2",
                url,
            )
            return None
        return html.encode("utf-8")
    except Exception as exc:
        logger.error("browser_fetcher Tier 1: patchright error for %s: %s", url, exc)
        return None
    finally:
        page.close()


def _is_cdp_chrome_available() -> bool:
    try:
        with socket.create_connection(("localhost", CDP_PORT), timeout=1):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _fetch_via_cdp(url: str, timeout: int) -> bytes | None:
    if not _is_cdp_chrome_available():
        logger.warning(
            "browser_fetcher Tier 2: Chrome CDP not available at %s. "
            "To enable: relaunch Chrome with --remote-debugging-port=9222 "
            "(quit Chrome first, then run: open -a 'Google Chrome' "
            "--args --remote-debugging-port=9222)",
            CDP_URL,
        )
        return None

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            if resp is None or resp.status >= 400:
                logger.warning(
                    "browser_fetcher Tier 2: HTTP %s for %s",
                    resp.status if resp else "None",
                    url,
                )
                return None
            html = page.content()
            if _is_cloudflare_challenge(html):
                logger.warning(
                    "browser_fetcher Tier 2: still got CF challenge for %s", url
                )
                return None
            return html.encode("utf-8")
        finally:
            page.close()
    except Exception as exc:
        logger.error("browser_fetcher Tier 2: CDP fetch error for %s: %s", url, exc)
        return None
    finally:
        pw.stop()


def fetch_html(url: str, timeout: int = 30) -> tuple[bytes | None, str]:
    """Fetch HTML for a URL using a browser. Two-tier escalation.

    Tier 1: patchright headed + persistent profile.
    Tier 2: CDP-attach to user's Chrome (if --remote-debugging-port=9222).

    Returns: (html_bytes_or_None, source_label)
        - html_bytes: bytes of the fetched HTML, or None if all tiers failed
        - source_label: one of 'patchright', 'cdp_attached', 'failed_all_tiers'
    """
    html = _fetch_via_patchright(url, timeout)
    if html is not None:
        return html, "patchright"

    html = _fetch_via_cdp(url, timeout)
    if html is not None:
        return html, "cdp_attached"

    return None, "failed_all_tiers"
