"""CLI entry point: python -m jd_matcher.dedup <command>

Commands:
    decide     -- Run dedup decision for a single posting (demo artifact for TASK-M2-008)
    calibrate  -- Calibrate C32 LLM gatekeeper against synthetic/real pairs (TASK-M2-012)
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


def _cmd_calibrate(args: argparse.Namespace) -> None:
    from jd_matcher.dedup.calibrate import run_calibration

    run_calibration(
        synthetic_only=args.synthetic_only,
        output_path=args.output,
    )


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        prog="python -m jd_matcher.dedup",
        description="C21 Two-Stage Dedup Engine + C32 Gatekeeper CLI",
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

    calibrate_parser = sub.add_parser(
        "calibrate",
        help="Calibrate C32 gatekeeper against synthetic and real labeled pairs",
    )
    calibrate_parser.add_argument(
        "--synthetic-only",
        action="store_true",
        help="Only use synthetic pairs (skip tests/fixtures/dedup_labels.csv)",
    )
    calibrate_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output report path (default: docs/poc/quality-logs/TASK-M2-012-calibration-report.md)",
    )

    args = parser.parse_args(argv)
    if args.command == "decide":
        _cmd_decide(args)
    elif args.command == "calibrate":
        _cmd_calibrate(args)


if __name__ == "__main__":
    main()
