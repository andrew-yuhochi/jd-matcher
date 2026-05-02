"""Run v7 extraction on the same 30 canonical IDs using gpt-4o (full model).

Model-ceiling test for TASK-M3-002. Same 30 IDs as v7-mini run.
Passes model_name="gpt-4o" to extract_canonical — this produces a fresh cache
miss because the cache key is (text_hash, model_name="gpt-4o", prompt_version="v7"),
which has never been populated.

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

# The same 30 canonical IDs as the v7-mini run in TASK-M3-002.md
CANONICAL_IDS = [
    344, 347, 350, 355, 357, 360, 366, 370, 380, 382,
    387, 389, 393, 397, 413, 417, 436, 448, 449, 450,
    465, 466, 474, 488, 489, 499, 522, 532, 534, 558,
]

# Cost watchdog: gpt-4o pricing as of 2025-08 is $2.50/1M input + $10.00/1M output.
# v5 run averaged ~8.3k input + ~300 output tokens per sample.
# 30 samples * (8300 * $2.50/1M + 300 * $10.00/1M) = 30 * ($0.02075 + $0.003) = ~$0.71
# Hard abort if cumulative cost exceeds $1.00.
COST_WATCHDOG_USD = 1.00
GPT4O_INPUT_COST_PER_TOKEN = 2.50 / 1_000_000
GPT4O_OUTPUT_COST_PER_TOKEN = 10.00 / 1_000_000


def fetch_canonical_data(conn: sqlite3.Connection, canonical_ids: list[int]) -> list[dict]:
    """Fetch canonical_postings rows for the given IDs."""
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
            print(f"  WARNING: canonical_id={cid} not found in canonical_postings")
            continue

        cid_val, company, title, full_jd = row

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


def estimate_call_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * GPT4O_INPUT_COST_PER_TOKEN
        + output_tokens * GPT4O_OUTPUT_COST_PER_TOKEN
    )


def fetch_ledger_cost_for_model(conn: sqlite3.Connection, model_name: str) -> float:
    """Sum cost_usd from llm_call_ledger for the given model (this session)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0.0) FROM llm_call_ledger WHERE model_name = ?",
        (model_name,),
    ).fetchone()
    return float(row[0]) if row else 0.0


def run_gpt4o_extraction(samples: list[dict]) -> tuple[list[dict], float]:
    """Run gpt-4o extraction on each sample.

    Returns (enriched_records, total_estimated_cost_usd).
    Aborts early if cumulative cost exceeds COST_WATCHDOG_USD.
    """
    results = []
    cumulative_cost = 0.0
    total = len(samples)

    for i, s in enumerate(samples, 1):
        cid = s["canonical_id"]
        pid = s["posting_id"]
        label = f"{s['company'][:30]} / {s['title'][:40]}"
        print(f"  [{i}/{total}] canonical_id={cid}: {label}")

        # Pre-run cost check (use running estimate)
        if cumulative_cost >= COST_WATCHDOG_USD:
            print(f"\n  ABORT: cumulative cost ${cumulative_cost:.4f} >= watchdog ${COST_WATCHDOG_USD:.2f}")
            print(f"  Completed {i-1}/{total} samples before abort.")
            break

        posting = PostingRow(
            id=pid,
            full_jd=s["full_jd"],
            canonical_company=s["company"] or None,
            canonical_title=s["title"] or None,
        )
        try:
            extraction = extract_canonical(posting, db_path=DB_PATH, model_name="gpt-4o")
            # Estimate cost for this sample (gpt-4o typical token counts)
            # We can't get exact per-call tokens from the return value, so we
            # read the ledger after each call.
            conn = sqlite3.connect(DB_PATH)
            try:
                total_ledger_cost = fetch_ledger_cost_for_model(conn, "gpt-4o")
            finally:
                conn.close()
            cumulative_cost = total_ledger_cost
            print(f"    fit={extraction.fit_score}  cumulative_cost=${cumulative_cost:.4f}")

            results.append({
                **s,
                "full_fit": extraction.fit_score,
                "full_fit_reasoning": extraction.fit_reasoning,
                "error": None,
            })
        except Exception as exc:
            print(f"    ERROR: {exc}")
            results.append({
                **s,
                "full_fit": None,
                "full_fit_reasoning": None,
                "error": str(exc),
            })

    return results, cumulative_cost


def main() -> None:
    print(f"DB: {DB_PATH}")
    print(f"Model: gpt-4o (full)")
    print(f"Prompt version: v7 (current _PROMPT_VERSION in extract.py)")
    print(f"Cost watchdog: ${COST_WATCHDOG_USD:.2f}")
    print(f"Canonical IDs ({len(CANONICAL_IDS)}): {CANONICAL_IDS}")

    conn = sqlite3.connect(DB_PATH)
    try:
        print("\nFetching canonical data...")
        samples = fetch_canonical_data(conn, CANONICAL_IDS)
    finally:
        conn.close()

    print(f"Fetched {len(samples)} samples (expected {len(CANONICAL_IDS)})")

    print("\nRunning gpt-4o v7 extraction (estimated 3-7 minutes for 30 samples)...")
    results, total_cost = run_gpt4o_extraction(samples)

    print(f"\nCompleted {len(results)} samples. Total cost: ${total_cost:.4f}")

    # Print raw JSON for capture
    print("\n--- RAW RESULTS JSON ---")
    for r in results:
        print(json.dumps({
            "canonical_id": r["canonical_id"],
            "company": r["company"],
            "title": r["title"],
            "full_fit": r["full_fit"],
            "full_fit_reasoning": r["full_fit_reasoning"],
            "error": r.get("error"),
        }, ensure_ascii=False))

    print(f"\nTotal estimated cost: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
