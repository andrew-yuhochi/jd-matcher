"""
CLI entry-point for the Gmail ingester.

Usage:
    python -m jd_matcher.ingest gmail --sender linkedin [--dry-run]
    python -m jd_matcher.ingest gmail --sender indeed  [--dry-run]

Set SKIP_LIVE=1 to read from tests/fixtures/gmail/ instead of calling Gmail.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_PATH = Path.home() / ".jd-matcher" / "tokens.json"
_DEFAULT_CLIENT_PATH = Path(
    os.environ.get("GMAIL_OAUTH_CLIENT_PATH", Path.home() / ".jd-matcher" / "credentials.json")
)
_DEFAULT_DB_PATH = Path(
    os.environ.get("DB_PATH", Path.home() / ".jd-matcher" / "jd-matcher.db")
)


def main() -> None:
    parser = argparse.ArgumentParser(description="jd-matcher Gmail ingester")
    sub = parser.add_subparsers(dest="command")

    gmail_cmd = sub.add_parser("gmail", help="Fetch emails from Gmail")
    gmail_cmd.add_argument(
        "--sender",
        required=True,
        choices=["linkedin", "indeed"],
        help="Sender filter key",
    )
    gmail_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print — do not write to DB",
    )
    gmail_cmd.add_argument(
        "--days",
        type=int,
        default=2,
        help="How many days back to fetch (default 2)",
    )

    args = parser.parse_args()

    if args.command == "gmail":
        _run_gmail(args)
    else:
        parser.print_help()


def _run_gmail(args: argparse.Namespace) -> None:
    from jd_matcher.ingest.gmail import GmailIngester

    skip_live = os.environ.get("SKIP_LIVE") == "1"

    credentials = None
    if not skip_live:
        from jd_matcher.auth.gmail_oauth import OAuthTokenInvalid, get_credentials

        if not _DEFAULT_CLIENT_PATH.exists():
            logger.error(
                "OAuth client secrets not found at %s. Set SKIP_LIVE=1 or run "
                "`python -m jd_matcher.auth` first.",
                _DEFAULT_CLIENT_PATH,
            )
            raise SystemExit(1)
        try:
            credentials = get_credentials(_DEFAULT_CLIENT_PATH, _DEFAULT_TOKEN_PATH)
        except OAuthTokenInvalid as exc:
            logger.error("%s", exc)
            raise SystemExit(1)

    db_path = _DEFAULT_DB_PATH
    if args.dry_run:
        # Use an in-memory DB so dry-run does not pollute the real DB.
        import tempfile

        _tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = Path(_tmp.name)
        _tmp.close()
        from jd_matcher.db.init_db import init_db

        init_db(db_path)
    else:
        from jd_matcher.db.init_db import init_db

        init_db(db_path)

    since_date = datetime.now(timezone.utc) - timedelta(days=args.days)
    ingester = GmailIngester(credentials, db_path)
    emails = ingester.fetch_for_sender(args.sender, since_date)

    mode = "SKIP_LIVE (fixtures)" if skip_live else "live Gmail"
    if args.dry_run:
        logger.info("[dry-run] mode=%s sender=%s fetched=%d", mode, args.sender, len(emails))
        for msg in emails:
            logger.info(
                "  id=%-20s sender=%r subject=%r received_at=%s",
                msg.id,
                msg.sender,
                msg.subject,
                msg.received_at.isoformat(),
            )
    else:
        logger.info("mode=%s sender=%s fetched=%d", mode, args.sender, len(emails))


if __name__ == "__main__":
    main()
