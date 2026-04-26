"""
C27 — Ingest Report CLI.

Usage:
    python -m jd_matcher.report ingest [--since YYYY-MM-DD] [--source X] [--format markdown|csv]

Renders a tabular report of email_ingest_log rows to stdout.
Read-only — never mutates the database.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from jd_matcher.db.email_ingest_log import query_email_ingest_log

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"

_COLUMNS = [
    "Date",
    "Source",
    "Subject",
    "URLs",
    "New",
    "Posts",
    "Hydrated",
    "Failed",
]


def _row_to_display(row: dict) -> dict[str, str]:
    received = row["received_at"] or ""
    date_part = received[:10] if received else ""
    subject = (row["subject"] or "")[:40]
    return {
        "Date": date_part,
        "Source": row["source"] or "",
        "Subject": subject,
        "URLs": str(row["urls_extracted_count"]),
        "New": str(row["urls_new_count"]),
        "Posts": str(row["postings_created_count"]),
        "Hydrated": str(row["postings_hydrated_count"]),
        "Failed": str(row["postings_hydration_failed_count"]),
    }


def _emit_markdown(rows: list[dict]) -> None:
    display = [_row_to_display(r) for r in rows]

    # Compute column widths from data + header.
    widths: dict[str, int] = {col: len(col) for col in _COLUMNS}
    for d in display:
        for col in _COLUMNS:
            widths[col] = max(widths[col], len(d[col]))

    # Also account for the totals row.
    totals = _compute_totals(rows)
    for col in _COLUMNS:
        widths[col] = max(widths[col], len(totals[col]))

    def _fmt_row(d: dict[str, str]) -> str:
        cells = [d[col].ljust(widths[col]) for col in _COLUMNS]
        return "| " + " | ".join(cells) + " |"

    sep = "| " + " | ".join("-" * widths[col] for col in _COLUMNS) + " |"

    print(_fmt_row({col: col for col in _COLUMNS}))
    print(sep)
    for d in display:
        print(_fmt_row(d))

    # Aggregate row.
    print(sep)
    print(_fmt_row(totals))


def _emit_csv(rows: list[dict]) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for d in [_row_to_display(r) for r in rows]:
        writer.writerow(d)
    writer.writerow(_compute_totals(rows))


def _compute_totals(rows: list[dict]) -> dict[str, str]:
    return {
        "Date": f"{len(rows)} emails",
        "Source": "",
        "Subject": "TOTAL",
        "URLs": str(sum(r["urls_extracted_count"] for r in rows)),
        "New": str(sum(r["urls_new_count"] for r in rows)),
        "Posts": str(sum(r["postings_created_count"] for r in rows)),
        "Hydrated": str(sum(r["postings_hydrated_count"] for r in rows)),
        "Failed": str(sum(r["postings_hydration_failed_count"] for r in rows)),
    }


def cmd_ingest(args: argparse.Namespace) -> None:
    db_path = Path(args.db) if getattr(args, "db", None) else _DEFAULT_DB_PATH
    rows = query_email_ingest_log(
        since=args.since,
        source=args.source,
        db_path=db_path,
    )
    if args.format == "csv":
        _emit_csv(rows)
    else:
        _emit_markdown(rows)


def main() -> None:
    parser = argparse.ArgumentParser(prog="jd-matcher report")
    parser.add_argument(
        "--db",
        default=None,
        help="Path to SQLite DB (default: ~/.jd-matcher/jd-matcher.db)",
    )
    subs = parser.add_subparsers(dest="cmd", required=True)

    ingest_parser = subs.add_parser("ingest", help="Show per-email ingest log")
    ingest_parser.add_argument(
        "--since",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Filter to emails received on or after this date",
    )
    ingest_parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Filter to emails from this source (e.g. linkedin, indeed)",
    )
    ingest_parser.add_argument(
        "--format",
        choices=["markdown", "csv"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    ingest_parser.set_defaults(func=cmd_ingest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
