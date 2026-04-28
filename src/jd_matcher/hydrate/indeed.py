"""Indeed JD Hydrator.

Fetches the full job description from Indeed's public job page:
    GET https://www.indeed.com/viewjob?jk={jk}

No authentication required.  The jk parameter is the Indeed job key extracted
from the posting URL.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, Optional

import requests
from bs4 import BeautifulSoup

from jd_matcher.hydrate._text import strip_html_to_text
from jd_matcher.hydrate.rate_limiter import HYDRATOR_RATE_LIMITER

logger = logging.getLogger(__name__)

_VIEWJOB_URL = "https://www.indeed.com/viewjob?jk={jk}"
_DEFAULT_FIXTURES_DIR = Path(__file__).parents[3] / "tests" / "fixtures" / "hydration" / "indeed"

# Full M1-005b stealth stack — all 9 items required.
# Missing any Sec-Fetch-* header produces Cloudflare 403 (confirmed empirically).
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
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-User": "?1",
}

_JK_RE = re.compile(r'[?&]jk=([a-zA-Z0-9][a-zA-Z0-9-]*)')
_INDEED_URL_RE = re.compile(r'indeed\.com/(?:viewjob|rc/clk)[?&][^"\'>\s]*jk=([a-zA-Z0-9][a-zA-Z0-9-]*)')


@dataclass
class HydratedIndeedJD:
    """Full job description fetched from an Indeed public page."""

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


def hydrate(url: str, fixtures_dir: Optional[Path] = None) -> HydratedIndeedJD:
    """Fetch and parse an Indeed job posting.

    When SKIP_LIVE=1 is set, reads from a local fixture file instead of
    making a real HTTP request.
    """
    job_id = _extract_job_id(url)
    if job_id is None:
        return HydratedIndeedJD(
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
    m = _JK_RE.search(url)
    if m:
        return m.group(1)
    m = _INDEED_URL_RE.search(url)
    if m:
        return m.group(1)
    # Plain alphanumeric job key passed directly
    plain_m = re.fullmatch(r'[a-zA-Z0-9]+', url.strip())
    if plain_m and len(url.strip()) >= 8:
        return url.strip()
    return None


def _load_from_fixture(url: str, job_id: str, fixtures_dir: Path) -> HydratedIndeedJD:
    candidates = [
        fixtures_dir / f"{job_id}.html",
        fixtures_dir / f"sample-{job_id}.html",
    ]
    for candidate in candidates:
        if candidate.exists():
            raw_html = candidate.read_bytes()
            logger.debug("indeed hydrate: loaded fixture %s", candidate)
            return _parse_html(raw_html, job_id, url)

    logger.warning(
        "indeed hydrate: no fixture found for job_id=%s in %s", job_id, fixtures_dir
    )
    return HydratedIndeedJD(
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


def _fetch_live(url: str, job_id: str) -> HydratedIndeedJD:
    """Make a real HTTP request to the Indeed viewjob page.

    Uses a Session with the full M1-005b stealth stack (9 headers) so that
    Cloudflare's browser-check heuristics pass. Bare requests.get() with only
    a User-Agent header produces 403 on production Indeed URLs.

    Auto-escalates to browser_fetcher when Cloudflare blocks the requests path
    (detected via 403 + Cf-Mitigated: challenge header).
    """
    fetch_url = _VIEWJOB_URL.format(jk=job_id)
    HYDRATOR_RATE_LIMITER.wait()
    session = requests.Session()
    session.headers.update(_STEALTH_HEADERS)
    try:
        resp = session.get(
            fetch_url,
            allow_redirects=True,
            timeout=30,
        )
    except requests.RequestException as exc:
        reason = f"request_error:{type(exc).__name__}"
        logger.error("indeed hydrate: network error job_id=%s — %s", job_id, exc)
        return HydratedIndeedJD(
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
    finally:
        session.close()

    raw_html = resp.content

    is_cf_blocked = (
        resp.status_code == 403
        and resp.headers.get("Cf-Mitigated") == "challenge"
    )

    if resp.status_code == 200 and not is_cf_blocked:
        return _parse_html(raw_html, job_id, url)

    if is_cf_blocked or resp.status_code in (403, 429, 503):
        logger.info(
            "indeed hydrate: requests path blocked (status=%s); "
            "escalating to browser_fetcher for job_id=%s",
            resp.status_code,
            job_id,
        )
        import jd_matcher.hydrate.browser_fetcher as _bf

        html_bytes, source = _bf.fetch_html(fetch_url)
        if html_bytes is None:
            return HydratedIndeedJD(
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
                failure_reason=f"browser_fetcher_failed_all_tiers (last requests={resp.status_code})",
            )
        logger.info(
            "indeed hydrate: browser_fetcher succeeded via %s for job_id=%s",
            source,
            job_id,
        )
        return _parse_html(html_bytes, job_id, url)

    reason = f"http_{resp.status_code}"
    if resp.status_code == 429:
        reason = "429_rate_limited"
    logger.warning(
        "indeed hydrate: HTTP %s for job_id=%s", resp.status_code, job_id
    )
    return HydratedIndeedJD(
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


def _parse_html(html_bytes: bytes, job_id: str, source_url: str) -> HydratedIndeedJD:
    """Extract JD fields from raw Indeed HTML.

    Strategy:
      1. JSON-LD <script type="application/ld+json"> with @type==JobPosting
      2. DOM scraping via BeautifulSoup
      3. If both fail: hydration_status='failed'
    """
    soup = BeautifulSoup(html_bytes, "html.parser")

    jd = _try_json_ld(soup, job_id, source_url, html_bytes)
    if jd is not None:
        return jd

    jd = _try_dom_scrape(soup, job_id, source_url, html_bytes)
    if jd is not None:
        return jd

    logger.warning("indeed hydrate: no parseable content for job_id=%s", job_id)
    return HydratedIndeedJD(
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
) -> Optional[HydratedIndeedJD]:
    for script in soup.find_all("script", type="application/ld+json"):
        raw_text = script.string or ""
        try:
            data = json.loads(raw_text)
        except (json.JSONDecodeError, ValueError):
            logger.debug(
                "indeed hydrate: malformed JSON-LD for job_id=%s, falling back to DOM",
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
        return HydratedIndeedJD(
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
) -> Optional[HydratedIndeedJD]:
    """Scrape JD fields from Indeed DOM."""
    title = (
        _text(soup, "h1.jobsearch-JobInfoHeader-title")
        or _text(soup, "[data-testid='jobsearch-JobInfoHeader-title']")
        or _text(soup, "h1")
    )
    company = (
        _text(soup, "[data-testid='inlineHeader-companyName']")
        or _text(soup, ".icl-u-lg-mr--sm.icl-u-xs-mr--xs")
        or _text(soup, ".jobsearch-InlineCompanyRating-companyHeader")
    )
    location = (
        _text(soup, "[data-testid='job-location']")
        or _text(soup, ".jobsearch-JobInfoHeader-subtitle .jobsearch-JobInfoHeader-locationWithDistance")
        or _text(soup, ".icl-IconFunctional--location + span")
    )
    description = (
        _text(soup, "#jobDescriptionText")
        or _text(soup, ".jobsearch-jobDescriptionText")
        or _text(soup, "[data-testid='jobsearch-jobDescriptionText']")
    )

    if title is None and company is None and description is None:
        return None

    status = _determine_status(title, description)
    return HydratedIndeedJD(
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
