"""CLI entry point for the JD Hydrator.

Usage:
    # Single URL — returns HydratedJD as JSON (uses SKIP_LIVE when set)
    python -m jd_matcher.hydrate <url>

    # Capture mode — fetches real HTML from a .eml file and saves fixtures
    python -m jd_matcher.hydrate --capture-real --from-eml <eml_path>
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import re
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _hydrate_single(url: str) -> None:
    from jd_matcher.hydrate.linkedin import hydrate as li_hydrate, HydratedJD
    from jd_matcher.hydrate.indeed import hydrate as in_hydrate

    # Infer source from URL
    if "indeed" in url.lower():
        result = in_hydrate(url)
    else:
        result = li_hydrate(url)

    def _serialise(obj: object) -> object:
        if hasattr(obj, "__dataclass_fields__"):
            d = dataclasses.asdict(obj)
            d["raw_html"] = f"<{len(obj.raw_html)} bytes>"  # type: ignore[attr-defined]
            return d
        if hasattr(obj, "isoformat"):
            return obj.isoformat()  # type: ignore[union-attr]
        return str(obj)

    print(json.dumps(dataclasses.asdict(result), default=_serialise, indent=2))


def _capture_real(eml_path: str) -> None:
    """Parse a .eml file, fetch each LinkedIn URL, and save HTML fixtures."""
    import email as _email_module
    import requests

    eml_bytes = Path(eml_path).read_bytes()
    # Re-use the LinkedIn email parser
    from jd_matcher.parse.linkedin_email import _LI_URL_RE as LI_RE

    decoded = eml_bytes.decode("utf-8", errors="replace")
    job_ids = list(dict.fromkeys(LI_RE.findall(decoded)))

    if not job_ids:
        print("No LinkedIn job IDs found in the .eml file.")
        return

    save_dir = Path("tests/fixtures/hydration/real")
    save_dir.mkdir(parents=True, exist_ok=True)

    browser_ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    guest_url_tpl = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

    succeeded = 0
    failed = 0
    total = len(job_ids)

    for idx, job_id in enumerate(job_ids, start=1):
        fetch_url = guest_url_tpl.format(job_id=job_id)
        out_path = save_dir / f"{job_id}.html"

        if idx > 1:
            print(f"  Waiting 30s before next request...")
            time.sleep(30)

        print(f"[{idx}/{total}] Fetching jobId {job_id}...", end="", flush=True)
        try:
            resp = requests.get(
                fetch_url,
                headers={"User-Agent": browser_ua},
                timeout=10,
            )
            html = resp.content
            out_path.write_bytes(html)
            size = len(html)
            print(f" saved ({size} bytes, status {resp.status_code})")
            if resp.status_code == 200:
                succeeded += 1
            else:
                failed += 1
                print(f"  WARNING: non-200 status {resp.status_code}")
        except Exception as exc:
            out_path.write_bytes(b"")
            failed += 1
            print(f" FAILED: {exc}")

    print(f"\nSummary: {succeeded}/{total} succeeded, {failed}/{total} failed")
    print(f"Fixtures saved to: {save_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m jd_matcher.hydrate")
    parser.add_argument("url", nargs="?", help="Job URL or job ID to hydrate")
    parser.add_argument("--capture-real", action="store_true", help="Capture mode")
    parser.add_argument("--from-eml", help="Path to .eml file (used with --capture-real)")
    args = parser.parse_args()

    if args.capture_real:
        if not args.from_eml:
            print("--capture-real requires --from-eml <path>", file=sys.stderr)
            sys.exit(1)
        _capture_real(args.from_eml)
    elif args.url:
        _hydrate_single(args.url)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
