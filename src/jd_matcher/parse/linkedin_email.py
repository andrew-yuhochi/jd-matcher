"""
LinkedIn alert email parser.

Extracts job posting URLs (primary) and best-effort title/company/location
(secondary) from LinkedIn job-alert RFC-822 messages.

Strategy:
  1. Prefer text/plain part for URL extraction — decoded via email module
     (handles quoted-printable automatically).
  2. Fall back to text/html part when no plain-text part exists.
  3. Best-effort title/company/location from HTML via BeautifulSoup.
  4. Canonical URL: strip all query params, normalise /comm/jobs/ → /jobs/.
"""

from __future__ import annotations

import email as _email_module
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

from jd_matcher.ingest.gmail import RawEmail

logger = logging.getLogger(__name__)

# Matches both /jobs/view/{id} and /comm/jobs/view/{id}.
_LI_URL_RE = re.compile(r'linkedin\.com/(?:comm/)?jobs/view/(\d+)')


@dataclass
class ParsedPosting:
    """One job posting extracted from an alert email."""

    source: Literal['linkedin', 'indeed']
    url: str           # canonical — no query params, no /comm/
    raw_url: str       # as found in the email body
    job_id: str
    title: Optional[str]
    company: Optional[str]
    location: Optional[str]
    received_at: datetime
    raw_body: bytes    # full RFC-822 message bytes for replay


def parse(raw_email: RawEmail) -> list[ParsedPosting]:
    """Extract all LinkedIn job postings from *raw_email*.

    Returns one :class:`ParsedPosting` per unique canonical URL found in the
    message.  Returns an empty list on malformed input (never raises).
    """
    try:
        return _parse(raw_email)
    except Exception:
        logger.exception(
            "linkedin_email.parse: unhandled error on message id=%s — skipped",
            raw_email.id,
        )
        return []


def _parse(raw_email: RawEmail) -> list[ParsedPosting]:
    msg = _email_module.message_from_bytes(raw_email.body_bytes)

    plain_text = _get_decoded_part(msg, 'text/plain')
    html_text = _get_decoded_part(msg, 'text/html')

    # Primary: plain-text; secondary: HTML when no plain-text part exists OR
    # when plain-text decoding yields no URLs (e.g. QP corruption of job IDs
    # that start with hex characters like 'abc', 'def').
    job_id_to_raw_url: dict[str, str] = {}

    if plain_text:
        for m in _LI_URL_RE.finditer(plain_text):
            job_id = m.group(1)
            if job_id not in job_id_to_raw_url:
                start = plain_text.rfind('http', 0, m.start())
                if start == -1:
                    raw_url_candidate = f"https://www.linkedin.com/jobs/view/{job_id}/"
                else:
                    end_bound = min(len(plain_text), start + 300)
                    raw_url_candidate = plain_text[start:end_bound].split()[0]
                job_id_to_raw_url[job_id] = raw_url_candidate

    # Fall back to HTML when plain-text had no usable URLs.
    extraction_source_for_log = 'text/plain'
    if not job_id_to_raw_url and html_text:
        extraction_source_for_log = 'text/html (fallback)'
        for m in _LI_URL_RE.finditer(html_text):
            job_id = m.group(1)
            if job_id not in job_id_to_raw_url:
                start = html_text.rfind('http', 0, m.start())
                if start == -1:
                    raw_url_candidate = f"https://www.linkedin.com/jobs/view/{job_id}/"
                else:
                    end_bound = min(len(html_text), start + 300)
                    raw_url_candidate = html_text[start:end_bound].split()[0]
                job_id_to_raw_url[job_id] = raw_url_candidate

    if not plain_text and not html_text:
        logger.warning(
            "linkedin_email.parse: no text/plain or text/html part in message id=%s",
            raw_email.id,
        )
        return []

    if not job_id_to_raw_url:
        logger.debug(
            "linkedin_email.parse: no LinkedIn job URLs found in message id=%s",
            raw_email.id,
        )
        return []

    # Build title/company/location lookup from HTML (best-effort).
    meta_by_job_id: dict[str, dict[str, Optional[str]]] = {}
    if html_text:
        meta_by_job_id = _extract_html_meta(html_text)

    postings: list[ParsedPosting] = []
    for job_id, raw_url in job_id_to_raw_url.items():
        canonical = f"https://linkedin.com/jobs/view/{job_id}"
        meta = meta_by_job_id.get(job_id, {})
        postings.append(
            ParsedPosting(
                source='linkedin',
                url=canonical,
                raw_url=raw_url,
                job_id=job_id,
                title=meta.get('title'),
                company=meta.get('company'),
                location=meta.get('location'),
                received_at=raw_email.received_at,
                raw_body=raw_email.body_bytes,
            )
        )
        logger.debug(
            "linkedin_email.parse: extracted job_id=%s canonical=%s",
            job_id,
            canonical,
        )

    url_only_count = sum(
        1 for p in postings if not p.title and not p.company and not p.location
    )
    if postings and url_only_count / len(postings) > 0.20:
        logger.warning(
            "linkedin_email.parse: URL-only fraction %.0f%% > 20%% in message id=%s",
            url_only_count / len(postings) * 100,
            raw_email.id,
        )

    return postings


def _get_decoded_part(msg: _email_module.message.Message, content_type: str) -> str:
    """Return the decoded text for the first part matching *content_type*.

    Uses get_payload(decode=True) which handles quoted-printable and base64
    transparently.  Returns empty string when no matching part exists.
    """
    if msg.get_content_type() == content_type:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_param('charset') or 'utf-8'
            return payload.decode(charset, errors='replace')
        return ''

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == content_type:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_param('charset') or 'utf-8'
                    return payload.decode(charset, errors='replace')
    return ''


def _extract_html_meta(html: str) -> dict[str, dict[str, Optional[str]]]:
    """Best-effort title/company/location extraction from HTML.

    Returns a dict keyed by job_id.  Missing fields are None.
    """
    soup = BeautifulSoup(html, 'html.parser')
    result: dict[str, dict[str, Optional[str]]] = {}

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        m = _LI_URL_RE.search(href)
        if not m:
            continue
        job_id = m.group(1)

        title_text: Optional[str] = a_tag.get_text(strip=True) or None

        # Walk siblings / parent to find company and location text nodes.
        company_text: Optional[str] = None
        location_text: Optional[str] = None

        # Try nearest text siblings in parent container.
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

        result[job_id] = {
            'title': title_text,
            'company': company_text,
            'location': location_text,
        }

    return result

