"""CLI entry point: python -m jd_matcher.dedup decide --posting-id N

Demo artifact for TASK-M2-008.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path.cwd() / ".env")


_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"


def _cmd_decide(args: argparse.Namespace) -> None:
    from jd_matcher.dedup.engine import decide

    decision = decide(posting_id=args.posting_id, db_path=args.db_path)
    print(decision.model_dump_json(indent=2))


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        prog="python -m jd_matcher.dedup",
        description="C21 Two-Stage Dedup Engine CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    decide_parser = sub.add_parser("decide", help="Run dedup decision for a single posting")
    decide_parser.add_argument(
        "--posting-id",
        type=int,
        required=True,
        help="ID of the posting in the postings table",
    )
    decide_parser.add_argument(
        "--db-path",
        type=Path,
        default=_DEFAULT_DB_PATH,
        help="Path to SQLite DB (default: ~/.jd-matcher/jd-matcher.db)",
    )

    args = parser.parse_args(argv)
    if args.command == "decide":
        _cmd_decide(args)


if __name__ == "__main__":
    main()
