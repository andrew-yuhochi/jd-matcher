# Run v8 prompt extraction on the same 30 canonical IDs as v7 runs, using gpt-4o-mini.
# Outputs per-sample fit_score, fit_reasoning, and cost summary.
# DO NOT COMMIT — scratch script.

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from jd_matcher.llm.extract import PostingRow, extract_canonical, _PROMPT_VERSION

logging.basicConfig(level=logging.WARNING)

DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"
MODEL = "gpt-4o-mini"

CANONICAL_IDS = [
    344, 347, 350, 355, 357, 360, 366, 370, 380, 382,
    387, 389, 393, 397, 413, 417, 436, 448, 449, 450,
    465, 466, 474, 488, 489, 499, 522, 532, 534, 558,
]


def fetch_samples(conn: sqlite3.Connection, canonical_ids: list[int]) -> list[dict]:
    results = []
    for cid in canonical_ids:
        row = conn.execute(
            """
            SELECT canonical_id, canonical_company, canonical_title, full_jd
            FROM canonical_postings
            WHERE canonical_id = ?
            """,
            (cid,),
        ).fetchone()
        if row is None:
            print(f"  WARNING: canonical_id={cid} not found")
            continue
        cid_val, company, title, full_jd = row
        if not full_jd:
            print(f"  WARNING: canonical_id={cid} has no full_jd")
            continue
        results.append({
            "canonical_id": cid_val,
            "company": company or "",
            "title": title or "",
            "full_jd": full_jd,
        })
    return results


def main() -> None:
    print(f"Prompt version: {_PROMPT_VERSION}")
    print(f"Model: {MODEL}")
    print(f"DB: {DB_PATH}")
    print(f"Canonical IDs: {len(CANONICAL_IDS)}")
    print("-" * 80)

    conn = sqlite3.connect(DB_PATH)
    try:
        samples = fetch_samples(conn, CANONICAL_IDS)
    finally:
        conn.close()

    print(f"Fetched {len(samples)} samples\n")

    # Query ledger cost before run to compute delta
    conn2 = sqlite3.connect(DB_PATH)
    cost_before = conn2.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_call_ledger"
    ).fetchone()[0]
    conn2.close()

    results = []
    total = len(samples)
    for i, s in enumerate(samples, 1):
        cid = s["canonical_id"]
        print(f"  [{i}/{total}] {cid}: {s['company'][:30]} / {s['title'][:40]}")

        # canonical_id=366 may hit the Hybrid—Other parse failure; catch and record ERR
        posting = PostingRow(
            id=cid,
            full_jd=s["full_jd"],
            canonical_company=s["company"] or None,
            canonical_title=s["title"] or None,
        )
        try:
            extraction = extract_canonical(posting, db_path=DB_PATH, model_name=MODEL)
            print(f"         fit={extraction.fit_score}  reasoning: {extraction.fit_reasoning[:100]}")
            results.append({
                "canonical_id": cid,
                "company": s["company"],
                "title": s["title"],
                "status": "OK",
                "fit_score": extraction.fit_score,
                "fit_reasoning": extraction.fit_reasoning,
            })
        except Exception as exc:
            print(f"         ERR: {exc}")
            results.append({
                "canonical_id": cid,
                "company": s["company"],
                "title": s["title"],
                "status": "ERR",
                "error": str(exc),
            })

    # Cost delta
    conn3 = sqlite3.connect(DB_PATH)
    cost_after = conn3.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_call_ledger"
    ).fetchone()[0]
    conn3.close()
    total_cost = cost_after - cost_before

    # Distribution
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    ok_count = 0
    for r in results:
        if r["status"] == "OK":
            dist[r["fit_score"]] += 1
            ok_count += 1

    print("\n" + "=" * 80)
    print(f"COMPLETED: {ok_count} / {len(CANONICAL_IDS)}")
    print(f"TOTAL COST: ${total_cost:.5f}")
    print(f"Distribution: {dist}")

    print("\n--- RAW RESULTS JSON ---")
    for r in results:
        print(json.dumps({
            "canonical_id": r["canonical_id"],
            "company": r["company"],
            "title": r["title"],
            "status": r["status"],
            "fit_score": r.get("fit_score"),
            "fit_reasoning": r.get("fit_reasoning"),
            "error": r.get("error"),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
