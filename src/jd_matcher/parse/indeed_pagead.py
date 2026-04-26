"""
Indeed pagead/clk URL resolver (C4 sub-step, TASK-M1-005b).

Resolves Indeed pagead/clk/dl redirect URLs to their canonical
viewjob?jk=<hex> form by following the redirect chain with a
browser-mimicking stealth header stack.

All 8 stealth-stack items per TDD §C4 Responsibility (3) are mandatory:
  (a) Session reuse across the batch
  (b) Browser-style User-Agent (Chrome on macOS)
  (c) Referer: https://mail.google.com/
  (d) Browser Accept / Accept-Language headers
  (e) html.unescape() BEFORE the HTTP request
  (f) 3.0–4.5s jitter between consecutive requests
  (g) allow_redirects=True, timeout=30
  (h) Discard tracking params — keep only jk=<hex>

Set JD_MATCHER_OFFLINE_PARSE=1 to skip all resolution (offline mode).
"""

from __future__ import annotations

import argparse
import email as _email_module
import logging
import os
import random
import re
import sys
import time
from html import unescape
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

logger = logging.getLogger(__name__)

_STEALTH_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://mail.google.com/",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_PAGEAD_RE = re.compile(r"pagead/clk", re.IGNORECASE)
_JK_RE = re.compile(r"[?&]jk=([a-f0-9]{16})")

# Tracking params to strip from resolved URLs — keep only jk=
_TRACKING_PARAMS = frozenset({"tk", "q", "l", "from", "ad", "mo", "pub"})


def _strip_tracking(url: str) -> str:
    """Return the canonical URL with only jk= preserved."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=False)

    jk_values = qs.get("jk")
    if not jk_values:
        return url

    jk = jk_values[0]
    canonical = urlunparse(
        parsed._replace(
            netloc="ca.indeed.com",
            path="/viewjob",
            query=f"jk={jk}",
            fragment="",
        )
    )
    return canonical


def _is_pagead(url: str) -> bool:
    return bool(_PAGEAD_RE.search(url))


def resolve_pagead_urls(
    urls: list[str],
    session: Optional[requests.Session] = None,
) -> dict[str, str]:
    """Resolve Indeed pagead/clk URLs to canonical viewjob?jk= URLs.

    Non-pagead URLs pass through unchanged (idempotent).
    Returns {original_url: canonical_url} for every input URL.

    When JD_MATCHER_OFFLINE_PARSE=1 is set, skips all HTTP and returns
    every URL unchanged.
    """
    if os.environ.get("JD_MATCHER_OFFLINE_PARSE") == "1":
        logger.debug("resolve_pagead_urls: offline mode — returning all URLs unchanged")
        return {u: u for u in urls}

    pagead_urls = [u for u in urls if _is_pagead(u)]
    passthrough = {u: u for u in urls if not _is_pagead(u)}

    if not pagead_urls:
        return passthrough

    logger.info(
        "resolve_pagead_urls: resolving %d pagead URL(s)", len(pagead_urls)
    )

    own_session = session is None
    if own_session:
        session = requests.Session()
    session.headers.update(_STEALTH_HEADERS)  # type: ignore[union-attr]

    resolved: dict[str, str] = {}
    for idx, original_url in enumerate(pagead_urls):
        # (e) html.unescape BEFORE the HTTP request
        unescaped = unescape(original_url)
        try:
            resp = session.get(  # type: ignore[union-attr]
                unescaped,
                allow_redirects=True,  # (g)
                timeout=30,            # (g)
            )
            final_url = resp.url
            m = _JK_RE.search(final_url)
            if m:
                canonical = _strip_tracking(final_url)
                resolved[original_url] = canonical
                logger.debug(
                    "resolve_pagead_urls: %s -> %s", original_url[:80], canonical
                )
            else:
                logger.warning(
                    "resolve_pagead_urls: no jk= in resolved URL %s (original: %s)",
                    final_url[:120],
                    original_url[:80],
                )
                resolved[original_url] = original_url
        except Exception as exc:
            logger.warning(
                "resolve_pagead_urls: failed to resolve %s — %s",
                original_url[:80],
                exc,
            )
            resolved[original_url] = original_url

        # (f) jitter between consecutive requests — skip after the last one
        if idx < len(pagead_urls) - 1:
            delay = 3 + random.uniform(0, 1.5)
            time.sleep(delay)

    if own_session:
        session.close()

    logger.info(
        "resolve_pagead_urls: done — %d/%d resolved to canonical",
        sum(1 for k, v in resolved.items() if v != k),
        len(pagead_urls),
    )

    return {**passthrough, **resolved}


def _extract_pagead_urls_from_eml(eml_path: Path) -> list[str]:
    """Extract all pagead/clk URLs from an .eml file's HTML part."""
    body_bytes = eml_path.read_bytes()
    msg = _email_module.message_from_bytes(body_bytes)

    pagead_url_re = re.compile(
        r'https?://[^"\'<>\s]*pagead/clk[^"\'<>\s]*', re.IGNORECASE
    )

    seen: set[str] = set()
    urls: list[str] = []

    for part in msg.walk():
        ct = part.get_content_type()
        if ct not in ("text/html", "text/plain"):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        for raw_url in pagead_url_re.findall(text):
            canonical_raw = unescape(raw_url)
            if canonical_raw not in seen:
                seen.add(canonical_raw)
                urls.append(canonical_raw)

    return urls


def _format_table(mapping: dict[str, str]) -> str:
    """Format {original: canonical} as a markdown table."""
    lines = ["| # | Original URL (truncated) | Canonical URL |", "|-|---|---|"]
    for i, (orig, canon) in enumerate(mapping.items(), 1):
        orig_display = orig[:80] + ("..." if len(orig) > 80 else "")
        lines.append(f"| {i} | {orig_display} | {canon} |")
    return "\n".join(lines)


def main() -> None:
    """CLI entry point: resolve pagead URLs from a real .eml file."""
    ap = argparse.ArgumentParser(
        description=(
            "Resolve Indeed pagead/clk URLs in an .eml file to canonical viewjob URLs."
        )
    )
    ap.add_argument("--eml", required=True, help="Path to an Indeed .eml file")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s %(message)s"
    )

    eml_path = Path(args.eml)
    if not eml_path.exists():
        print(f"ERROR: file not found: {eml_path}", file=sys.stderr)
        sys.exit(1)

    pagead_urls = _extract_pagead_urls_from_eml(eml_path)
    print(f"Found {len(pagead_urls)} unique pagead URL(s) in {eml_path.name}")
    print()

    if not pagead_urls:
        print("No pagead URLs to resolve.")
        return

    mapping = resolve_pagead_urls(pagead_urls)
    print(_format_table(mapping))
    print()

    resolved_count = sum(1 for k, v in mapping.items() if v != k)
    print(f"Resolved: {resolved_count}/{len(pagead_urls)}")


if __name__ == "__main__":
    main()
