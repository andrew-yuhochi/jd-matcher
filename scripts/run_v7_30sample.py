"""Run v7 extraction on the same 30 canonical IDs used for v5/v6 30-sample validation.

Ownership-based rubric scoring done inline. Outputs per-sample table for appending
to TASK-M3-002.md quality log.

DO NOT COMMIT — scratch script.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

# Ensure project src is on the path
_PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from jd_matcher.llm.extract import PostingRow, extract_canonical

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"

# The 30 canonical IDs from TASK-M3-002.md v5/v6 30-sample validation
CANONICAL_IDS = [
    344, 347, 350, 355, 357, 360, 366, 370, 380, 382,
    387, 389, 393, 397, 413, 417, 436, 448, 449, 450,
    465, 466, 474, 488, 489, 499, 522, 532, 534, 558,
]


def fetch_canonical_data(conn: sqlite3.Connection, canonical_ids: list[int]) -> list[dict]:
    """Fetch canonical_postings rows for the 30 IDs."""
    results = []
    for cid in canonical_ids:
        row = conn.execute(
            """
            SELECT canonical_id, canonical_company, canonical_title,
                   fit_score, role_orientation, industry, full_jd
            FROM canonical_postings
            WHERE canonical_id = ?
            """,
            (cid,),
        ).fetchone()
        if row is None:
            print(f"  WARNING: canonical_id={cid} not found in canonical_postings")
            continue

        cid_val, company, title, v_fit, v_orient, v_industry, full_jd = row

        if not full_jd:
            print(f"  WARNING: canonical_id={cid} has no full_jd")
            continue

        results.append({
            "canonical_id": cid_val,
            "company": company or "",
            "title": title or "",
            "posting_id": cid_val,
            "full_jd": full_jd,
        })
    return results


def run_v7_extraction(samples: list[dict]) -> list[dict]:
    """Run v7 extraction on each sample, return enriched records."""
    results = []
    total = len(samples)
    for i, s in enumerate(samples, 1):
        cid = s["canonical_id"]
        pid = s["posting_id"]
        print(f"  [{i}/{total}] canonical_id={cid}: {s['company'][:30]} / {s['title'][:40]}")

        posting = PostingRow(
            id=pid,
            full_jd=s["full_jd"],
            canonical_company=s["company"] or None,
            canonical_title=s["title"] or None,
        )
        try:
            extraction = extract_canonical(posting, db_path=DB_PATH)
            results.append({
                **s,
                "v7_fit": extraction.fit_score,
                "v7_role_orientation": json.dumps(extraction.role_orientation),
                "v7_industry": extraction.industry,
                "v7_fit_reasoning": extraction.fit_reasoning,
                "error": None,
            })
        except Exception as exc:
            print(f"    ERROR: {exc}")
            results.append({
                **s,
                "v7_fit": None,
                "v7_role_orientation": None,
                "v7_industry": None,
                "v7_fit_reasoning": None,
                "error": str(exc),
            })
    return results


def main() -> None:
    print(f"DB: {DB_PATH}")
    print(f"Canonical IDs ({len(CANONICAL_IDS)}): {CANONICAL_IDS}")

    conn = sqlite3.connect(DB_PATH)
    try:
        print("\nFetching canonical data...")
        samples = fetch_canonical_data(conn, CANONICAL_IDS)
    finally:
        conn.close()

    print(f"Fetched {len(samples)} samples (expected {len(CANONICAL_IDS)})")

    print("\nRunning v7 extraction (this will take 2-5 minutes for 30 samples)...")
    results = run_v7_extraction(samples)

    # Print raw JSON for capture
    print("\n--- RAW RESULTS JSON ---")
    for r in results:
        print(json.dumps({
            "canonical_id": r["canonical_id"],
            "company": r["company"],
            "title": r["title"],
            "v7_fit": r["v7_fit"],
            "v7_role_orientation": r["v7_role_orientation"],
            "v7_industry": r["v7_industry"],
            "v7_fit_reasoning": r["v7_fit_reasoning"],
            "error": r.get("error"),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
