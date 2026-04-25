"""
Indeed alert email parser.

Extracts job posting URLs from Indeed job-alert RFC-822 messages.

URL patterns handled:
  - Direct viewjob:  ca.indeed.com/viewjob?jk={jobKey}[&...]
  - rc/clk redirect: ca.indeed.com/rc/clk?jk={jobKey}[&...]
  - rt subdomain:    rt.indeed.com/...?jk={jobKey}[&...]
  - alert subdomain: alert.indeed.com/...?jk={jobKey}[&...]

Canonical URL: https://ca.indeed.com/viewjob?jk={jobKey}
The `jk` query parameter is the canonical job identifier.

Strategy mirrors linkedin_email.py: prefer text/plain; fall back to text/html.
"""

from __future__ import annotations

import email as _email_module
import logging
import re
from datetime import datetime, timezone
from typing import Literal, Optional
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from jd_matcher.ingest.gmail import RawEmail
from jd_matcher.parse.linkedin_email import ParsedPosting, _get_decoded_part

logger = logging.getLogger(__name__)

# Matches any Indeed URL that carries a jk= parameter (job key).
# Covers: ca.indeed.com/viewjob, ca.indeed.com/rc/clk, rt.indeed.com/...,
# alert.indeed.com/..., and plain indeed.com/viewjob variants.
_INDEED_URL_RE = re.compile(
    r'https?://(?:[a-z]+\.)?indeed\.com/[^\s"\'<>]*?jk=([a-z0-9]+)',
    re.IGNORECASE,
)


def parse(raw_email: RawEmail) -> list[ParsedPosting]:
    """Extract all Indeed job postings from *raw_email*.

    Returns one :class:`ParsedPosting` per unique canonical URL.
    Returns an empty list on malformed input (never raises).
    """
    try:
        return _parse(raw_email)
    except Exception:
        logger.exception(
            "indeed_email.parse: unhandled error on message id=%s — skipped",
            raw_email.id,
        )
        return []


def _parse(raw_email: RawEmail) -> list[ParsedPosting]:
    msg = _email_module.message_from_bytes(raw_email.body_bytes)

    plain_text = _get_decoded_part(msg, 'text/plain')
    html_text = _get_decoded_part(msg, 'text/html')

    # Primary: plain-text; secondary: HTML when no plain-text part exists OR
    # when plain-text QP decoding corrupts URLs (job keys starting with hex chars).
    job_key_to_raw_url: dict[str, str] = {}

    if plain_text:
        for m in _INDEED_URL_RE.finditer(plain_text):
            job_key = m.group(1).lower()
            if job_key not in job_key_to_raw_url:
                job_key_to_raw_url[job_key] = m.group(0)

    # Fall back to HTML when plain-text had no usable URLs.
    if not job_key_to_raw_url and html_text:
        for m in _INDEED_URL_RE.finditer(html_text):
            job_key = m.group(1).lower()
            if job_key not in job_key_to_raw_url:
                job_key_to_raw_url[job_key] = m.group(0)

    if not plain_text and not html_text:
        logger.warning(
            "indeed_email.parse: no text/plain or text/html part in message id=%s",
            raw_email.id,
        )
        return []

    if not job_key_to_raw_url:
        logger.debug(
            "indeed_email.parse: no Indeed job URLs found in message id=%s",
            raw_email.id,
        )
        return []

    meta_by_job_key: dict[str, dict[str, Optional[str]]] = {}
    if html_text:
        meta_by_job_key = _extract_html_meta(html_text)

    postings: list[ParsedPosting] = []
    for job_key, raw_url in job_key_to_raw_url.items():
        canonical = f"https://ca.indeed.com/viewjob?jk={job_key}"
        meta = meta_by_job_key.get(job_key, {})
        postings.append(
            ParsedPosting(
                source='indeed',
                url=canonical,
                raw_url=raw_url,
                job_id=job_key,
                title=meta.get('title'),
                company=meta.get('company'),
                location=meta.get('location'),
                received_at=raw_email.received_at,
                raw_body=raw_email.body_bytes,
            )
        )
        logger.debug(
            "indeed_email.parse: extracted job_key=%s canonical=%s",
            job_key,
            canonical,
        )

    url_only_count = sum(
        1 for p in postings if not p.title and not p.company and not p.location
    )
    if postings and url_only_count / len(postings) > 0.20:
        logger.warning(
            "indeed_email.parse: URL-only fraction %.0f%% > 20%% in message id=%s",
            url_only_count / len(postings) * 100,
            raw_email.id,
        )

    return postings


def _extract_html_meta(html: str) -> dict[str, dict[str, Optional[str]]]:
    """Best-effort title/company/location from HTML links containing jk=."""
    soup = BeautifulSoup(html, 'html.parser')
    result: dict[str, dict[str, Optional[str]]] = {}

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        m = _INDEED_URL_RE.search(href)
        if not m:
            continue
        job_key = m.group(1).lower()

        title_text: Optional[str] = a_tag.get_text(strip=True) or None

        company_text: Optional[str] = None
        location_text: Optional[str] = None

        parent = a_tag.parent
        if parent:
            siblings = [
                s.get_text(strip=True)
                for s in parent.next_siblings
                if hasattr(s, 'get_text') and s.get_text(strip=True)
            ]
            if siblings:
                company_text = siblings[0]
            if len(siblings) > 1:
                location_text = siblings[1]

        result[job_key] = {
            'title': title_text,
            'company': company_text,
            'location': location_text,
        }

    return result
