"""Run v6 extraction on the same 30 canonical IDs used for v5 30-sample validation.

Canonical IDs sourced from TASK-M3-002.md § v5 30-Sample Scale Validation.
Outputs: per-sample table with v5_fit, v6_fit, role_orientation, industry.
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

# The 30 canonical IDs from TASK-M3-002.md v5 30-sample validation
CANONICAL_IDS = [
    344, 347, 350, 355, 357, 360, 366, 370, 380, 382,
    387, 389, 393, 397, 413, 417, 436, 448, 449, 450,
    465, 466, 474, 488, 489, 499, 522, 532, 534, 558,
]


def fetch_canonical_data(conn: sqlite3.Connection, canonical_ids: list[int]) -> list[dict]:
    """Fetch canonical_postings rows — full_jd lives directly on canonical_postings."""
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

        cid_val, company, title, v5_fit, v5_orient, v5_industry, full_jd = row

        if not full_jd:
            print(f"  WARNING: canonical_id={cid} has no full_jd")
            continue

        results.append({
            "canonical_id": cid_val,
            "company": company or "",
            "title": title or "",
            "posting_id": cid_val,  # use canonical_id as the PostingRow id
            "full_jd": full_jd,
            "v5_fit": v5_fit,
            "v5_role_orientation": v5_orient,
            "v5_industry": v5_industry,
        })
    return results


def run_v6_extraction(samples: list[dict]) -> list[dict]:
    """Run v6 extraction on each sample, return enriched records."""
    results = []
    total = len(samples)
    for i, s in enumerate(samples, 1):
        cid = s["canonical_id"]
        pid = s["posting_id"]
        print(f"  [{i}/{total}] canonical_id={cid} posting_id={pid}: {s['company'][:30]} / {s['title'][:40]}")

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
                "v6_fit": extraction.fit_score,
                "v6_role_orientation": json.dumps(extraction.role_orientation),
                "v6_industry": extraction.industry,
                "v6_fit_reasoning": extraction.fit_reasoning,
                "error": None,
            })
        except Exception as exc:
            print(f"    ERROR: {exc}")
            results.append({
                **s,
                "v6_fit": None,
                "v6_role_orientation": None,
                "v6_industry": None,
                "v6_fit_reasoning": None,
                "error": str(exc),
            })
    return results


# ---------------------------------------------------------------------------
# Rubric scoring: apply v6 5-line rubric to each sample
# Based on v5 per-sample analysis in TASK-M3-002.md + role knowledge
# ---------------------------------------------------------------------------

# Pre-computed rubric_expected from prior analysis in quality log.
# Key = canonical_id, value = expected fit_score per v6 rubric.
# Sources:
#   - fit=2 cases: IBM SAP HANA, Marine Biologics, Human Data Manager (all confirmed correct in v5 spot-check)
#   - fit=5 cases: ExaCare AI MLE (confirmed correct in v5 spot-check)
#   - Amazon SDE-II (417): debated at 3-4 in v5 analysis; use 3 (conservative, primarily SWE)
#   - Remaining cases scored from v5 distribution context + role title/company signals
#   - v5 reported distribution: 0 at 1, 3 at 2, 8 at 3, 12 at 4, 7 at 5
RUBRIC_EXPECTED: dict[int, int] = {
    # confirmed fit=2 in v5 spot-check
    389: 2,  # IBM SAP HANA Package Consultant
    393: 2,  # Marine Biologics Senior Scientist
    355: 2,  # Human Data Manager Early Career
    # confirmed fit=5 in v5 spot-check
    466: 5,  # ExaCare AI Machine Learning Engineer
    # Amazon SDE-II — debated 3-4; use 3 (primarily SWE)
    417: 3,
    # UBC Postdoc (534) — research scientist, pure DS/stats work → 5
    534: 5,
    # Turing Quantitative Finance (532) — quant/financial modeling → 3
    532: 3,
    # ICBC RPA/AI Apps Developer (474) — primarily dev/automation → 3
    474: 3,
    # Remaining 22 samples: use v5 fit_score as proxy rubric_expected
    # (v5 distribution was assessed as healthy; no systematic mis-anchoring noted
    # for these cases in the quality log — only Amazon, IBM, Marine Biologics,
    # Human Data, ExaCare AI, UBC, Turing, ICBC were individually called out)
    # These will be filled from v5_fit at runtime for the non-spot-checked cases
}


def apply_rubric_expected(results: list[dict]) -> list[dict]:
    """Fill rubric_expected for each sample."""
    for r in results:
        cid = r["canonical_id"]
        if cid in RUBRIC_EXPECTED:
            r["rubric_expected"] = RUBRIC_EXPECTED[cid]
        else:
            # Use v5_fit as rubric baseline for unreviewed cases
            r["rubric_expected"] = r["v5_fit"]
    return results


def print_comparison_table(results: list[dict]) -> None:
    """Print side-by-side comparison table."""
    print("\n" + "=" * 110)
    print(f"{'canonical_id':>12} {'employer/title (truncated)':40} {'v5':>4} {'v6':>4} {'rubric':>6} {'agree?':>7}")
    print("-" * 110)

    agree_v5 = 0
    agree_v6 = 0
    valid_count = 0

    for r in results:
        if r["v6_fit"] is None:
            label = f"{r['company'][:18]}/{r['title'][:18]}"
            print(f"{r['canonical_id']:>12} {label:40} {str(r['v5_fit']):>4} {'ERR':>4} {str(r['rubric_expected']):>6} {'N/A':>7}")
            continue

        label = f"{r['company'][:18]}/{r['title'][:18]}"
        v5_match = "Y" if r["v5_fit"] == r["rubric_expected"] else "N"
        v6_match = "Y" if r["v6_fit"] == r["rubric_expected"] else "N"
        print(
            f"{r['canonical_id']:>12} {label:40} "
            f"{str(r['v5_fit']):>4} {str(r['v6_fit']):>4} "
            f"{str(r['rubric_expected']):>6} "
            f"{'v5='+v5_match+',v6='+v6_match:>10}"
        )
        valid_count += 1
        if r["v5_fit"] == r["rubric_expected"]:
            agree_v5 += 1
        if r["v6_fit"] == r["rubric_expected"]:
            agree_v6 += 1

    print("=" * 110)
    if valid_count > 0:
        v5_agree_rate = agree_v5 / valid_count
        v6_agree_rate = agree_v6 / valid_count
        print(f"\nAggregate (n={valid_count} valid extractions):")
        print(f"  v5 agreement rate: {agree_v5}/{valid_count} = {v5_agree_rate:.1%}")
        print(f"  v6 agreement rate: {agree_v6}/{valid_count} = {v6_agree_rate:.1%}")
        v5_disagree_rate = 1 - v5_agree_rate
        v6_disagree_rate = 1 - v6_agree_rate
        print(f"  v5 disagreement rate: {v5_disagree_rate:.1%}")
        print(f"  v6 disagreement rate: {v6_disagree_rate:.1%}")


def print_score_distribution(results: list[dict]) -> None:
    """Print fit_score distribution for v5 and v6."""
    v5_dist: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    v6_dist: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in results:
        if r["v5_fit"] is not None and r["v5_fit"] in v5_dist:
            v5_dist[r["v5_fit"]] += 1
        if r["v6_fit"] is not None and r["v6_fit"] in v6_dist:
            v6_dist[r["v6_fit"]] += 1

    print("\nfit_score distribution:")
    print(f"  {'Score':>5} {'v5 count':>10} {'v6 count':>10}")
    for score in [1, 2, 3, 4, 5]:
        print(f"  {score:>5} {v5_dist[score]:>10} {v6_dist[score]:>10}")


def print_notable_shifts(results: list[dict]) -> None:
    """Print cases where v6 changed vs v5."""
    shifts = [r for r in results if r["v6_fit"] is not None and r["v6_fit"] != r["v5_fit"]]
    if not shifts:
        print("\nNotable shifts: none (v6 == v5 on all samples)")
        return

    print(f"\nNotable shifts (v6 != v5) — {len(shifts)} cases:")
    for r in shifts:
        direction = "UP" if r["v6_fit"] > r["v5_fit"] else "DOWN"
        rubric = r["rubric_expected"]
        v5_correct = "v5 correct" if r["v5_fit"] == rubric else f"v5 wrong (rubric={rubric})"
        v6_correct = "v6 correct" if r["v6_fit"] == rubric else f"v6 wrong (rubric={rubric})"
        reasoning_snippet = (r["v6_fit_reasoning"] or "")[:100]
        print(
            f"  canonical_id={r['canonical_id']} {r['company'][:20]}/{r['title'][:30]}: "
            f"v5={r['v5_fit']} → v6={r['v6_fit']} ({direction}) | {v5_correct} | {v6_correct}"
        )
        print(f"    v6 reasoning: {reasoning_snippet}")


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

    # Check v5 fit_score availability
    missing_v5 = [s for s in samples if s["v5_fit"] is None]
    if missing_v5:
        print(f"  WARNING: {len(missing_v5)} samples have no v5 fit_score in canonical_postings")

    print("\nRunning v6 extraction...")
    results = run_v6_extraction(samples)
    results = apply_rubric_expected(results)

    print_comparison_table(results)
    print_score_distribution(results)
    print_notable_shifts(results)

    # Raw JSON for quality log
    print("\n--- RAW RESULTS JSON (for quality log) ---")
    for r in results:
        print(json.dumps({
            "canonical_id": r["canonical_id"],
            "company": r["company"],
            "title": r["title"],
            "v5_fit": r["v5_fit"],
            "v6_fit": r["v6_fit"],
            "rubric_expected": r["rubric_expected"],
            "v6_role_orientation": r["v6_role_orientation"],
            "v6_industry": r["v6_industry"],
            "v6_fit_reasoning": r["v6_fit_reasoning"],
        }))


if __name__ == "__main__":
    main()
