"""LinkedIn JD Hydrator.

Fetches the full job description from LinkedIn's public guest endpoint:
    GET https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jobId}

No authentication, no cookie, no LinkedIn account required.
The guest endpoint is ToS-gray at personal volume (~40 req/day) — acknowledged
in DATA-SOURCES.md §"LinkedIn JD Hydration".
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal, Optional

import requests
from bs4 import BeautifulSoup

from jd_matcher.hydrate._text import strip_html_to_text
from jd_matcher.hydrate.rate_limiter import HYDRATOR_RATE_LIMITER

logger = logging.getLogger(__name__)

_GUEST_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
_DEFAULT_FIXTURES_DIR = Path(__file__).parents[3] / "tests" / "fixtures" / "hydration" / "linkedin"
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_JOB_ID_RE = re.compile(r'linkedin\.com/(?:comm/)?jobs/view/([\w-]+)')


@dataclass
class HydratedJD:
    """Full job description fetched from a public guest endpoint."""

    url: str
    job_id: str
    title: Optional[str]
    company: Optional[str]
    location: Optional[str]
    description: Optional[str]
    posted_date: Optional[date]
    seniority_level: Optional[str]
    employment_type: Optional[str]
    industries: Optional[list[str]]
    raw_html: bytes
    hydration_status: Literal["complete", "partial", "failed"]
    failure_reason: Optional[str]


def hydrate(url: str, fixtures_dir: Optional[Path] = None) -> HydratedJD:
    """Fetch and parse a LinkedIn job posting.

    When SKIP_LIVE=1 is set, reads from a local fixture file instead of
    making a real HTTP request.  The fixture filename is derived from the
    job_id embedded in *url* (e.g. ``4405645363.html``).
    """
    job_id = _extract_job_id(url)
    if job_id is None:
        return HydratedJD(
            url=url,
            job_id="",
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
            failure_reason="no_job_id_in_url",
        )

    if os.environ.get("SKIP_LIVE") == "1":
        return _load_from_fixture(url, job_id, fixtures_dir or _DEFAULT_FIXTURES_DIR)

    return _fetch_live(url, job_id)


def _extract_job_id(url: str) -> Optional[str]:
    m = _JOB_ID_RE.search(url)
    if m:
        return m.group(1)
    # Also handle guest endpoint URL format
    guest_m = re.search(r'/jobPosting/([\w-]+)', url)
    if guest_m:
        return guest_m.group(1)
    # Plain numeric job id passed directly
    plain_m = re.fullmatch(r'\d+', url.strip())
    if plain_m:
        return url.strip()
    # Try matching sample-NNN fixture naming for demo CLI
    sample_m = re.search(r'SAMPLE(\d+)', url, re.IGNORECASE)
    if sample_m:
        return f"sample-{int(sample_m.group(1)):03d}"
    return None


def _load_from_fixture(url: str, job_id: str, fixtures_dir: Path) -> HydratedJD:
    """Load HTML from a local fixture file."""
    candidates = [
        fixtures_dir / f"{job_id}.html",
        fixtures_dir / f"sample-{job_id}.html",
    ]
    for candidate in candidates:
        if candidate.exists():
            raw_html = candidate.read_bytes()
            logger.debug("linkedin hydrate: loaded fixture %s", candidate)
            return _parse_html(raw_html, job_id, url)

    logger.warning(
        "linkedin hydrate: no fixture found for job_id=%s in %s", job_id, fixtures_dir
    )
    return HydratedJD(
        url=url,
        job_id=job_id,
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
        failure_reason="fixture_not_found",
    )


def _fetch_live(url: str, job_id: str) -> HydratedJD:
    """Make a real HTTP request to the LinkedIn guest endpoint."""
    guest_url = _GUEST_URL.format(job_id=job_id)
    HYDRATOR_RATE_LIMITER.wait()
    try:
        resp = requests.get(
            guest_url,
            headers={"User-Agent": _BROWSER_UA},
            timeout=10,
        )
    except requests.RequestException as exc:
        reason = f"request_error:{type(exc).__name__}"
        logger.error(
            "linkedin hydrate: network error job_id=%s — %s", job_id, exc
        )
        return HydratedJD(
            url=url,
            job_id=job_id,
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
            failure_reason=reason,
        )

    raw_html = resp.content
    if resp.status_code != 200:
        reason = f"http_{resp.status_code}"
        if resp.status_code == 429:
            reason = "429_rate_limited"
        logger.warning(
            "linkedin hydrate: HTTP %s for job_id=%s", resp.status_code, job_id
        )
        return HydratedJD(
            url=url,
            job_id=job_id,
            title=None,
            company=None,
            location=None,
            description=None,
            posted_date=None,
            seniority_level=None,
            employment_type=None,
            industries=None,
            raw_html=raw_html,
            hydration_status="failed",
            failure_reason=reason,
        )

    return _parse_html(raw_html, job_id, url)


def _parse_html(html_bytes: bytes, job_id: str, source_url: str) -> HydratedJD:
    """Extract JD fields from raw HTML.

    Strategy:
      1. JSON-LD <script type="application/ld+json"> with @type==JobPosting
      2. DOM scraping via BeautifulSoup CSS selectors
      3. If both fail: hydration_status='failed', failure_reason='no_parseable_content'
    """
    soup = BeautifulSoup(html_bytes, "html.parser")

    # Attempt 1: JSON-LD
    jd = _try_json_ld(soup, job_id, source_url, html_bytes)
    if jd is not None:
        return jd

    # Attempt 2: DOM scraping
    jd = _try_dom_scrape(soup, job_id, source_url, html_bytes)
    if jd is not None:
        return jd

    logger.warning(
        "linkedin hydrate: no parseable content for job_id=%s", job_id
    )
    return HydratedJD(
        url=source_url,
        job_id=job_id,
        title=None,
        company=None,
        location=None,
        description=None,
        posted_date=None,
        seniority_level=None,
        employment_type=None,
        industries=None,
        raw_html=html_bytes,
        hydration_status="failed",
        failure_reason="no_parseable_content",
    )


def _try_json_ld(
    soup: BeautifulSoup, job_id: str, source_url: str, raw_html: bytes
) -> Optional[HydratedJD]:
    """Parse JobPosting from JSON-LD <script> blocks."""
    for script in soup.find_all("script", type="application/ld+json"):
        raw_text = script.string or ""
        try:
            data = json.loads(raw_text)
        except (json.JSONDecodeError, ValueError):
            # Malformed JSON-LD — fall through to DOM
            logger.debug(
                "linkedin hydrate: malformed JSON-LD for job_id=%s, falling back to DOM",
                job_id,
            )
            continue

        if not isinstance(data, dict):
            continue
        if data.get("@type") != "JobPosting":
            continue

        title = data.get("title") or None
        company = None
        hiring_org = data.get("hiringOrganization")
        if isinstance(hiring_org, dict):
            company = hiring_org.get("name") or None

        location = None
        job_location = data.get("jobLocation")
        if isinstance(job_location, dict):
            address = job_location.get("address", {})
            if isinstance(address, dict):
                location = (
                    address.get("addressLocality")
                    or address.get("addressRegion")
                    or address.get("addressCountry")
                    or None
                )
        elif isinstance(job_location, list) and job_location:
            first_loc = job_location[0]
            if isinstance(first_loc, dict):
                address = first_loc.get("address", {})
                if isinstance(address, dict):
                    location = address.get("addressLocality") or None

        description_raw = data.get("description") or None
        description = strip_html_to_text(description_raw) if description_raw else None
        seniority_level = data.get("occupationalCategory") or None
        employment_type = data.get("employmentType") or None
        industries = data.get("industry")
        if isinstance(industries, str):
            industries = [industries] if industries else None

        posted_date = None
        date_str = data.get("datePosted") or data.get("validThrough")
        if date_str:
            try:
                posted_date = date.fromisoformat(str(date_str)[:10])
            except (ValueError, TypeError):
                pass

        status = _determine_status(title, description)
        return HydratedJD(
            url=source_url,
            job_id=job_id,
            title=title,
            company=company,
            location=location,
            description=description,
            posted_date=posted_date,
            seniority_level=seniority_level,
            employment_type=employment_type,
            industries=industries,
            raw_html=raw_html,
            hydration_status=status,
            failure_reason=None,
        )

    return None


def _try_dom_scrape(
    soup: BeautifulSoup, job_id: str, source_url: str, raw_html: bytes
) -> Optional[HydratedJD]:
    """Scrape JD fields from DOM using LinkedIn guest-page CSS selectors."""
    title = (
        _text(soup, "h1.top-card-layout__title")
        or _text(soup, ".topcard__title")
    )
    company = (
        _text(soup, ".topcard__org-name-link")
        or _text(soup, ".topcard__flavor:not(.topcard__flavor--bullet)")
    )
    location = _text(soup, ".topcard__flavor--bullet")
    description = (
        _description_text(soup, ".show-more-less-html__markup")
        or _description_text(soup, ".description__text")
    )

    if title is None and company is None and description is None:
        return None

    status = _determine_status(title, description)
    return HydratedJD(
        url=source_url,
        job_id=job_id,
        title=title,
        company=company,
        location=location,
        description=description,
        posted_date=None,
        seniority_level=None,
        employment_type=None,
        industries=None,
        raw_html=raw_html,
        hydration_status=status,
        failure_reason=None,
    )


def _determine_status(
    title: Optional[str], description: Optional[str]
) -> Literal["complete", "partial", "failed"]:
    if title and description:
        return "complete"
    if title or description:
        return "partial"
    return "failed"


def _text(soup: BeautifulSoup, selector: str) -> Optional[str]:
    el = soup.select_one(selector)
    if el is None:
        return None
    text = el.get_text(separator=" ", strip=True)
    return text or None


def _description_text(soup: BeautifulSoup, selector: str) -> Optional[str]:
    """Extract description-level content with paragraph breaks preserved."""
    el = soup.select_one(selector)
    if el is None:
        return None
    # Pass the element's inner HTML to strip_html_to_text so block elements
    # (<p>, <li>, <br>) become \n\n / \n separators rather than being
    # collapsed by BeautifulSoup's default get_text(separator=" ").
    inner_html = el.decode_contents()
    text = strip_html_to_text(inner_html)
    return text or None
