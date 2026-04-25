"""
CLI entry point for the email parsers.

Usage:
    python -m jd_matcher.parse --fixture linkedin/sample-001.eml
    python -m jd_matcher.parse --fixture indeed/sample-001.eml

Outputs a JSON array of ParsedPosting objects to stdout.
SKIP_LIVE=1 is implied — this command operates on synthetic fixtures only.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(name)s %(message)s')

_FIXTURES_ROOT = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "gmail"


def _make_serializable(obj: object) -> object:
    """Recursively make dataclass / datetime objects JSON-serialisable."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        d = dataclasses.asdict(obj)  # type: ignore[call-overload]
        return {k: _make_serializable(v) for k, v in d.items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return f"<bytes len={len(obj)}>"
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(i) for i in obj]
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a single .eml fixture file.")
    parser.add_argument(
        '--fixture',
        required=True,
        help="Relative path inside tests/fixtures/gmail/, e.g. linkedin/sample-001.eml",
    )
    args = parser.parse_args()

    fixture_path = _FIXTURES_ROOT / args.fixture
    if not fixture_path.exists():
        print(f"ERROR: fixture not found at {fixture_path}", file=sys.stderr)
        sys.exit(1)

    body_bytes = fixture_path.read_bytes()

    import email as _email_stdlib
    from email.header import decode_header, make_header
    from email.utils import parsedate_to_datetime
    from datetime import timezone

    msg = _email_stdlib.message_from_bytes(body_bytes)
    sender_raw = msg.get("From", "")
    subject_raw = msg.get("Subject", "")

    def _dh(raw: str) -> str:
        try:
            return str(make_header(decode_header(raw)))
        except Exception:
            return raw

    sender = _dh(sender_raw)
    subject = _dh(subject_raw)
    date_str = msg.get("Date", "")
    try:
        received_at = parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        received_at = datetime.now(timezone.utc)

    from jd_matcher.ingest.gmail import RawEmail

    raw_email = RawEmail(
        id=fixture_path.stem,
        sender=sender,
        subject=subject,
        received_at=received_at,
        body_bytes=body_bytes,
    )

    source_dir = args.fixture.split('/')[0].lower()

    if source_dir == 'linkedin':
        from jd_matcher.parse.linkedin_email import parse
    elif source_dir == 'indeed':
        from jd_matcher.parse.indeed_email import parse
    else:
        print(f"ERROR: unknown source directory '{source_dir}'", file=sys.stderr)
        sys.exit(1)

    postings = parse(raw_email)
    print(json.dumps([_make_serializable(p) for p in postings], indent=2))


if __name__ == '__main__':
    main()
