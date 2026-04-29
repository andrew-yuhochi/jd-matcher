"""Phase D re-extraction script for TASK-M2-006b.

Clears extraction_cache for all C19-passed postings and re-extracts them
using the updated canonical_extraction_v1.txt prompt (with the 43-entry
canonical taxonomy and soft-skill exclusion instruction).

After extraction, writes canonical fields back to the postings table.

Usage:
    .venv/bin/python scripts/reextract_canonical.py \\
        [--db ~/.jd-matcher/jd-matcher.db] \\
        [--dry-run]
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import date
from pathlib import Path

# Project root is 2 levels up from scripts/
_PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from jd_matcher.filter.title_filter import filter_title
from jd_matcher.llm.extract import (
    ExtractionParseError,
    PostingRow,
    extract_canonical,
)
from jd_matcher.llm.validate import _bust_cache_for_ids as _bust_cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".jd-matcher" / "jd-matcher.db"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_c19_passed(db_path: Path) -> list[dict]:
    """Return all postings with full_jd that pass the C19 title filter."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                p.id,
                p.canonical_title,
                p.canonical_company,
                p.canonical_location,
                p.full_jd
            FROM postings p
            WHERE p.full_jd IS NOT NULL AND p.full_jd != ''
            ORDER BY p.id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    passing = []
    filtered = 0
    for row in rows:
        title = row["canonical_title"] or ""
        decision = filter_title(title)
        if decision.action == "pass":
            passing.append(dict(row))
        else:
            filtered += 1

    logger.info(
        "fetch: %d total postings with full_jd; %d pass C19 filter; %d filtered",
        len(rows),
        len(passing),
        filtered,
    )
    return passing


def _write_canonical_to_postings(
    db_path: Path,
    posting_id: int,
    extraction,
) -> None:
    """Write canonical fields from extraction back to the postings table."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            UPDATE postings SET
                canonical_title       = ?,
                canonical_company     = ?,
                canonical_location    = ?,
                seniority_band        = ?,
                team_or_department    = ?,
                top_skills            = ?,
                role_summary          = ?
            WHERE id = ?
            """,
            (
                extraction.canonical_title,
                extraction.canonical_company,
                extraction.canonical_location,
                extraction.canonical_seniority,
                extraction.team_or_department,
                json.dumps(extraction.top_skills),
                extraction.role_summary,
                posting_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _total_cost_since(db_path: Path, start_iso: str) -> float:
    """Sum cost_usd from llm_call_ledger for rows added today."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_call_ledger "
            "WHERE called_at >= ? AND status = 'success'",
            (start_iso,),
        ).fetchone()
        return float(row[0]) if row else 0.0
    finally:
        conn.close()


def _count_ledger_rows(db_path: Path, start_iso: str) -> tuple[int, int]:
    """Return (new_api_calls, cache_hits) since start_iso."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM llm_call_ledger "
            "WHERE called_at >= ? GROUP BY status",
            (start_iso,),
        ).fetchall()
    finally:
        conn.close()
    new_calls = 0
    cache_hits = 0
    for status, cnt in rows:
        if status == "success":
            new_calls += cnt
        elif status == "cache_hit":
            cache_hits += cnt
    return new_calls, cache_hits


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(db_path: Path, dry_run: bool = False) -> None:
    from datetime import datetime, timezone

    run_start = datetime.now(timezone.utc).isoformat()

    postings = _fetch_c19_passed(db_path)
    posting_ids = [p["id"] for p in postings]

    print(f"\n{'DRY RUN — ' if dry_run else ''}Re-extraction plan:")
    print(f"  C19-passed postings to re-extract: {len(posting_ids)}")
    print(f"  DB: {db_path}")

    if dry_run:
        for p in postings[:5]:
            print(f"  ID={p['id']:>3}  {(p['canonical_company'] or ''):<30}  {p['canonical_title']}")
        if len(postings) > 5:
            print(f"  ... and {len(postings) - 5} more")
        print("\nDRY RUN complete — no DB changes made.")
        return

    # Step 1: bust extraction_cache for all C19-passed postings
    print(f"\nStep 1: clearing extraction_cache for {len(posting_ids)} postings …")
    deleted = _bust_cache(db_path, posting_ids)
    print(f"  Deleted {deleted} extraction_cache rows.")

    # Step 2: re-extract
    print(f"\nStep 2: re-extracting {len(posting_ids)} postings …")
    success_count = 0
    failure_count = 0
    failures: list[tuple[int, str]] = []

    for i, p in enumerate(postings, 1):
        posting_row = PostingRow(
            id=p["id"],
            full_jd=p["full_jd"],
            canonical_title=p["canonical_title"],
            canonical_company=p["canonical_company"],
            canonical_location=p["canonical_location"],
        )
        priors: dict[str, str] = {}
        if p["canonical_company"]:
            priors["company"] = p["canonical_company"]
        if p["canonical_title"]:
            priors["title"] = p["canonical_title"]
        if p["canonical_location"]:
            priors["location"] = p["canonical_location"]

        try:
            extraction = extract_canonical(
                posting_row,
                db_path=db_path,
                priors=priors or None,
            )
            _write_canonical_to_postings(db_path, p["id"], extraction)
            success_count += 1
            if i % 10 == 0 or i == len(postings):
                print(f"  [{i:>3}/{len(postings)}] OK  — ID={p['id']:>3}  {extraction.canonical_company}")
        except ExtractionParseError as exc:
            failure_count += 1
            failures.append((p["id"], str(exc)))
            logger.error("  FAIL — posting %d: %s", p["id"], exc)
        except Exception as exc:
            failure_count += 1
            failures.append((p["id"], str(exc)))
            logger.error("  FAIL — posting %d: %s", p["id"], exc)

    # Step 3: cost report
    total_cost = _total_cost_since(db_path, run_start)
    new_calls, cache_hits = _count_ledger_rows(db_path, run_start)

    print(f"\n{'='*60}")
    print(f"Re-extraction complete ({date.today().isoformat()})")
    print(f"  Postings attempted:  {len(posting_ids)}")
    print(f"  Successful:          {success_count}")
    print(f"  Failed:              {failure_count}")
    print(f"  New API calls:       {new_calls}")
    print(f"  Cache hits:          {cache_hits}")
    print(f"  Total cost (run):    ${total_cost:.6f}")

    if failures:
        print(f"\nFailures:")
        for pid, reason in failures:
            print(f"  ID={pid}: {reason[:100]}")

    if failure_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase D: re-extract canonical fields with updated prompt")
    parser.add_argument("--db", type=Path, default=_DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true", help="Print plan without making changes")
    args = parser.parse_args()

    main(db_path=args.db, dry_run=args.dry_run)
