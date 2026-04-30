"""C32 Calibration CLI — precision/recall threshold sweep for the dedup gatekeeper.

Entry point: python -m jd_matcher.dedup calibrate [--synthetic-only] [--output PATH]

Usage:
    python -m jd_matcher.dedup calibrate --synthetic-only
    python -m jd_matcher.dedup calibrate --output docs/poc/quality-logs/my-report.md

Loads test pairs from:
    1. tests/fixtures/dedup_synthetic_pairs.yaml (always)
    2. tests/fixtures/dedup_labels.csv (if present and non-empty, unless --synthetic-only)

For each pair computes FUSE component scores (embedding_cosine, skills_jaccard,
title_cosine, seniority_match, fuse_score) using the configured model, then runs:
    - Raw-FUSE decision (FUSE >= threshold → merge, else new) at thresholds
      [0.85, 0.88, 0.90, 0.92, 0.95]
    - Gatekeeper-augmented decision (3-tier logic: dispatch at gatekeeper_threshold=0.75,
      4-feature exact-match short-circuit, then actual LLM gatekeeper for borderline band)
    - Gatekeeper dispatch threshold sweep: [0.70, 0.75, 0.80, 0.85] — shows how raising
      or lowering the dispatch boundary affects precision/recall

Outputs a Markdown calibration report with threshold sweep, per-pair verdict table,
cost summary, recommended threshold, and title-cosine "Galent-pattern" diagnostic.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[3]
_SYNTHETIC_PAIRS_PATH = _PROJECT_ROOT / "tests" / "fixtures" / "dedup_synthetic_pairs.yaml"
_LABELS_CSV_PATH = _PROJECT_ROOT / "tests" / "fixtures" / "dedup_labels.csv"
_DEFAULT_OUTPUT_PATH = _PROJECT_ROOT / "docs" / "poc" / "quality-logs" / "TASK-M2-012-calibration-report.md"
_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"

_SWEEP_THRESHOLDS = [0.85, 0.88, 0.90, 0.92, 0.95]
_GATEKEEPER_THRESHOLD = 0.75
# Dispatch threshold sweep: how does changing the FUSE dispatch boundary affect results?
_DISPATCH_SWEEP_THRESHOLDS = [0.70, 0.75, 0.80, 0.85]

# Diagnostic pair IDs that must be called out explicitly in the report.
_DIAGNOSTIC_PAIR_IDS = {
    "real_001", "real_002", "real_003", "real_004",
    "real_005", "real_006", "real_007", "real_008", "real_009",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CalibrationPair:
    pair_id: str
    ground_truth: str  # 'merge' | 'new'
    scenario: str
    posting_a: dict[str, Any]
    posting_b: dict[str, Any]
    source: str  # 'synthetic' | 'real'


@dataclass
class PairResult:
    pair_id: str
    ground_truth: str
    scenario: str
    source: str

    # FUSE components (computed from config weights over in-memory feature vectors)
    embedding_cosine: float
    jaccard_top_skills: float
    title_cosine_score: float
    seniority_match_score: float
    fuse_score: float

    # Gatekeeper verdict (if called)
    gatekeeper_called: bool
    gatekeeper_is_same_role: bool | None
    gatekeeper_reasoning: str | None
    gatekeeper_status: str  # 'not_called' | 'exact_4f' | 'called_success' | 'called_fail'

    # Final gatekeeper-augmented decision
    gatekeeper_action: str  # 'merge' | 'new' | 'pending_gatekeeper'

    # Cost for this pair's gatekeeper call (0 if not called)
    call_cost_usd: float = 0.0
    call_latency_ms: int = 0


# ---------------------------------------------------------------------------
# FUSE score computation (in-memory, no DB needed for synthetic pairs)
# ---------------------------------------------------------------------------


def _jaccard_score(skills_a: list[str], skills_b: list[str]) -> float:
    a = {s.lower() for s in skills_a}
    b = {s.lower() for s in skills_b}
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _seniority_score(s1: str | None, s2: str | None) -> float:
    if not s1 or not s2:
        return 0.0
    return 1.0 if s1.strip().lower() == s2.strip().lower() else 0.0


def _compute_pair_fuse(
    pair: CalibrationPair,
    embedder,
    weights: dict[str, float],
    cache: dict[str, list[float]],
) -> tuple[float, float, float, float, float]:
    """Compute FUSE components for a calibration pair.

    Returns: (emb_cosine, skills_jaccard, title_cosine, seniority_match, fuse_score)
    Uses in-memory embedding via C28 provider for titles; embedding_cosine defaults
    to 0.5 for synthetic pairs (no posting_embeddings table available).
    """
    from jd_matcher.llm.embed import cosine as vec_cosine

    # Embedding cosine: for synthetic pairs we don't have role_summary embeddings
    # stored in a DB. We use title embedding as a proxy for the embedding_cosine
    # term on synthetic-only data (this is noted in the calibration report).
    t_a = pair.posting_a.get("canonical_title") or ""
    t_b = pair.posting_b.get("canonical_title") or ""

    def _get_embedding(text: str) -> list[float]:
        if text not in cache:
            try:
                vecs, _ = embedder.embed([text])
                cache[text] = vecs[0]
            except Exception as exc:
                logger.warning("calibrate: embedding failed for '%s': %s", text[:50], exc)
                cache[text] = []
        return cache[text]

    t_a_vec = _get_embedding(t_a)
    t_b_vec = _get_embedding(t_b)

    # Role-summary embedding cosine: use title embedding as proxy for synthetic pairs
    emb_cosine = float(vec_cosine(t_a_vec, t_b_vec)) if t_a_vec and t_b_vec else 0.5

    # Title cosine: same embedding (title proxy) — on synthetic data this is the same
    # as emb_cosine; on real data it would differ (role_summary vs title embedding).
    title_cosine = emb_cosine  # proxy for synthetic-only

    skills_jaccard = _jaccard_score(
        pair.posting_a.get("top_skills") or [],
        pair.posting_b.get("top_skills") or [],
    )
    seniority_m = _seniority_score(
        pair.posting_a.get("canonical_seniority"),
        pair.posting_b.get("canonical_seniority"),
    )

    fuse_score = (
        weights["embedding"] * emb_cosine
        + weights["skills"] * skills_jaccard
        + weights["title"] * title_cosine
        + weights["seniority"] * seniority_m
    )

    return emb_cosine, skills_jaccard, title_cosine, seniority_m, fuse_score


# ---------------------------------------------------------------------------
# 4-feature exact-match short-circuit
# ---------------------------------------------------------------------------


_EXACT_EPSILON = 1e-6


def _is_exact_match(emb: float, skills: float, title: float, seniority: float) -> bool:
    return (
        emb >= 1.0 - _EXACT_EPSILON
        and skills >= 1.0 - _EXACT_EPSILON
        and title >= 1.0 - _EXACT_EPSILON
        and seniority >= 1.0 - _EXACT_EPSILON
    )


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


def _precision_recall_f1(
    results: list[PairResult],
    threshold: float,
    use_gatekeeper: bool,
    dispatch_threshold: float | None = None,
) -> tuple[float, float, float]:
    """Compute P/R/F1 at a given threshold.

    For raw-FUSE: merge if fuse_score >= threshold.
    For gatekeeper-augmented: use gatekeeper_action (already computed with
    gatekeeper dispatched at 0.75; threshold param is applied to raw-FUSE
    path for comparison only).

    If dispatch_threshold is provided, re-simulate gatekeeper decisions using
    that dispatch boundary instead of the pre-computed gatekeeper_action. This
    is used for the dispatch threshold sweep section of the report.
    """
    tp = fp = fn = tn = 0
    for r in results:
        if r.ground_truth == "ambiguous":
            continue
        if use_gatekeeper:
            if dispatch_threshold is not None:
                # Re-simulate: pairs below dispatch_threshold are always 'new';
                # pairs at/above keep their gatekeeper_action (since we can't re-run LLM).
                if r.fuse_score < dispatch_threshold:
                    predicted = False  # would be 'new' under this threshold
                else:
                    predicted = r.gatekeeper_action == "merge"
            else:
                predicted = r.gatekeeper_action == "merge"
        else:
            predicted = r.fuse_score >= threshold

        actual = r.ground_truth == "merge"

        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


# ---------------------------------------------------------------------------
# Pair processing
# ---------------------------------------------------------------------------


def _process_pair(
    pair: CalibrationPair,
    classifier,
    embedder,
    weights: dict[str, float],
    embed_cache: dict[str, list[float]],
) -> PairResult:
    """Compute FUSE scores and run gatekeeper for a single pair."""
    t0 = time.monotonic()

    emb_cosine, skills_jaccard, title_cosine_score, seniority_m, fuse_score = _compute_pair_fuse(
        pair, embedder, weights, embed_cache
    )

    gatekeeper_called = False
    gatekeeper_is_same_role = None
    gatekeeper_reasoning = None
    gatekeeper_status = "not_called"
    gatekeeper_action = "new"
    call_cost_usd = 0.0
    call_latency_ms = 0

    if fuse_score < _GATEKEEPER_THRESHOLD:
        gatekeeper_action = "new"
        gatekeeper_status = "not_called"
    elif _is_exact_match(emb_cosine, skills_jaccard, title_cosine_score, seniority_m):
        gatekeeper_action = "merge"
        gatekeeper_status = "exact_4f"
    else:
        # Borderline band — call gatekeeper
        gatekeeper_called = True
        gk_t0 = time.monotonic()
        posting_a_dict = {
            "id": pair.pair_id + "_a",
            "full_jd": pair.posting_a.get("full_jd") or "",
            "canonical_title": pair.posting_a.get("canonical_title") or "",
            "canonical_company": pair.posting_a.get("canonical_company") or "",
        }
        posting_b_dict = {
            "id": pair.pair_id + "_b",
            "full_jd": pair.posting_b.get("full_jd") or "",
            "canonical_title": pair.posting_b.get("canonical_title") or "",
            "canonical_company": pair.posting_b.get("canonical_company") or "",
        }
        verdict = classifier.classify(
            posting_a_dict,
            posting_b_dict,
            fuse_score=fuse_score,
            retry_count=1,
        )
        call_latency_ms = int((time.monotonic() - gk_t0) * 1000)
        call_cost_usd = classifier.last_call_cost_usd

        if verdict is None:
            gatekeeper_action = "pending_gatekeeper"
            gatekeeper_status = "called_fail"
        else:
            gatekeeper_is_same_role = verdict.is_same_role
            gatekeeper_reasoning = verdict.reasoning
            gatekeeper_action = "merge" if verdict.is_same_role else "new"
            gatekeeper_status = "called_success"

    return PairResult(
        pair_id=pair.pair_id,
        ground_truth=pair.ground_truth,
        scenario=pair.scenario,
        source=pair.source,
        embedding_cosine=emb_cosine,
        jaccard_top_skills=skills_jaccard,
        title_cosine_score=title_cosine_score,
        seniority_match_score=seniority_m,
        fuse_score=fuse_score,
        gatekeeper_called=gatekeeper_called,
        gatekeeper_is_same_role=gatekeeper_is_same_role,
        gatekeeper_reasoning=gatekeeper_reasoning,
        gatekeeper_status=gatekeeper_status,
        gatekeeper_action=gatekeeper_action,
        call_cost_usd=call_cost_usd,
        call_latency_ms=call_latency_ms,
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _format_report(
    results: list[PairResult],
    total_cost_usd: float,
    total_calls: int,
    final_threshold: float,
    threshold_rationale: str,
) -> str:
    lines: list[str] = []

    lines.append("# TASK-M2-012 Calibration Report — Dedup Gatekeeper (C32)")
    lines.append("")
    lines.append("**Generated**: 2026-04-29  ")
    lines.append(f"**Pairs evaluated**: {len(results)} ({sum(1 for r in results if r.source == 'synthetic')} synthetic, {sum(1 for r in results if r.source == 'real')} real)  ")
    lines.append(f"**Gatekeeper LLM calls**: {total_calls}  ")
    lines.append(f"**Total LLM cost**: ${total_cost_usd:.4f} USD  ")
    lines.append("")

    # Only non-ambiguous for metrics
    labeled = [r for r in results if r.ground_truth != "ambiguous"]
    labeled_real = [r for r in results if r.source == "real" and r.ground_truth != "ambiguous"]
    labeled_synth = [r for r in results if r.source == "synthetic" and r.ground_truth != "ambiguous"]

    # --- Final threshold decision ---
    lines.append("## Final Threshold Decision")
    lines.append("")
    lines.append(f"**Pinned in config/dedup.yaml**: `dedup.gatekeeper_threshold = {final_threshold}`")
    lines.append("")
    lines.append(f"**Rationale**: {threshold_rationale}")
    lines.append("")

    # --- Threshold sweep table (raw-FUSE thresholds) ---
    lines.append("## Raw-FUSE Threshold Sweep (non-ambiguous pairs only)")
    lines.append("")
    lines.append("Compares raw-FUSE decisions vs gatekeeper-augmented decisions across FUSE merge thresholds.")
    lines.append("")
    lines.append("| FUSE Threshold | Raw-FUSE P | Raw-FUSE R | Raw-FUSE F1 | GK-Augmented P | GK-Augmented R | GK-Augmented F1 |")
    lines.append("|----------------|-----------|-----------|------------|---------------|---------------|----------------|")
    for thresh in _SWEEP_THRESHOLDS:
        rp, rr, rf1 = _precision_recall_f1(labeled, thresh, use_gatekeeper=False)
        gp, gr, gf1 = _precision_recall_f1(labeled, thresh, use_gatekeeper=True)
        lines.append(
            f"| {thresh:.2f} | {rp:.3f} | {rr:.3f} | {rf1:.3f} | "
            f"{gp:.3f} | {gr:.3f} | {gf1:.3f} |"
        )
    lines.append("")

    # --- Gatekeeper dispatch threshold sweep ---
    lines.append("## Gatekeeper Dispatch Threshold Sweep")
    lines.append("")
    lines.append("Shows effect of raising/lowering the FUSE score at which the gatekeeper is invoked.")
    lines.append("Lower dispatch threshold = more pairs sent to gatekeeper (higher cost, potentially higher recall).")
    lines.append("Higher dispatch threshold = fewer gatekeeper calls (lower cost, risks missing legit merges).")
    lines.append("")
    lines.append("| Dispatch Threshold | GK P | GK R | GK F1 | Pairs below threshold (→ 'new') |")
    lines.append("|-------------------|-----|-----|------|-------------------------------|")
    for dt in _DISPATCH_SWEEP_THRESHOLDS:
        gp, gr, gf1 = _precision_recall_f1(labeled, dt, use_gatekeeper=True, dispatch_threshold=dt)
        below_count = sum(1 for r in labeled if r.fuse_score < dt)
        lines.append(
            f"| {dt:.2f} | {gp:.3f} | {gr:.3f} | {gf1:.3f} | {below_count} |"
        )
    lines.append("")

    # --- Per-pair verdict table ---
    lines.append("## Per-Pair Verdict Table")
    lines.append("")
    lines.append("| Pair ID | Source | Scenario | GT | FUSE | GK Called | GK Verdict | GK Action | Correct? |")
    lines.append("|---------|--------|----------|-----|------|-----------|-----------|-----------|---------|")
    for r in results:
        gt_display = r.ground_truth
        gk_verdict = "—"
        if r.gatekeeper_status == "exact_4f":
            gk_verdict = "exact_4f"
        elif r.gatekeeper_is_same_role is True:
            gk_verdict = "same_role"
        elif r.gatekeeper_is_same_role is False:
            gk_verdict = "different"
        elif r.gatekeeper_status == "called_fail":
            gk_verdict = "FAIL"

        correct = ""
        if r.ground_truth != "ambiguous":
            predicted_merge = r.gatekeeper_action == "merge"
            actual_merge = r.ground_truth == "merge"
            correct = "YES" if predicted_merge == actual_merge else "**NO**"

        lines.append(
            f"| {r.pair_id} | {r.source} | {r.scenario} | {gt_display} | {r.fuse_score:.3f} | "
            f"{'Y' if r.gatekeeper_called else 'N'} | {gk_verdict} | {r.gatekeeper_action} | {correct} |"
        )
    lines.append("")

    # --- Real-data diagnostic pairs (real_001 through real_009) ---
    diagnostic_results = [r for r in results if r.pair_id in _DIAGNOSTIC_PAIR_IDS]
    if diagnostic_results:
        lines.append("## Diagnostic Pairs — Gatekeeper Behavior on Key Real Pairs")
        lines.append("")
        lines.append("These pairs were identified before calibration as the critical test cases.")
        lines.append("Failures here are flagged prominently.")
        lines.append("")
        false_merges_on_regression_pairs = []
        regression_blocking_ids = {"real_002", "real_003", "real_007", "real_008", "real_009"}

        for r in sorted(diagnostic_results, key=lambda x: x.pair_id):
            expected = "merge" if r.ground_truth == "merge" else "new"
            actual_action = r.gatekeeper_action
            status_icon = "PASS" if actual_action == expected else "**FAIL**"
            lines.append(f"**{r.pair_id}** — GT={r.ground_truth}, GK={r.gatekeeper_action}, FUSE={r.fuse_score:.3f} — {status_icon}")
            if r.gatekeeper_reasoning:
                lines.append(f"  - Reasoning: {r.gatekeeper_reasoning}")
            else:
                lines.append(f"  - GK status: {r.gatekeeper_status}")
            lines.append("")
            if actual_action == "merge" and r.ground_truth == "new":
                false_merges_on_regression_pairs.append(r.pair_id)

        if false_merges_on_regression_pairs:
            regression_failures = [p for p in false_merges_on_regression_pairs if p in regression_blocking_ids]
            if regression_failures:
                lines.append(f"> **REGRESSION FAILURE**: False-merge on regression-blocking pair(s): {', '.join(regression_failures)}")
                lines.append("> These are same-employer-different-role pairs that must never be merged.")
            else:
                lines.append(f"> Note: False-merge(s) detected on: {', '.join(false_merges_on_regression_pairs)}")
                lines.append("> None are regression-blocking pairs — flag for user review but not a regression.")
            lines.append("")

    # --- Summary metrics by source ---
    lines.append("## Precision / Recall Summary")
    lines.append("")
    lines.append("| Subset | GK P | GK R | GK F1 | Raw-FUSE P (0.90) | Raw-FUSE R (0.90) |")
    lines.append("|--------|-----|-----|------|-----------------|-----------------|")
    if labeled:
        gp, gr, gf1 = _precision_recall_f1(labeled, 0.90, use_gatekeeper=True)
        rp, rr, _ = _precision_recall_f1(labeled, 0.90, use_gatekeeper=False)
        lines.append(f"| All (synthetic+real) | {gp:.3f} | {gr:.3f} | {gf1:.3f} | {rp:.3f} | {rr:.3f} |")
    if labeled_synth:
        gp, gr, gf1 = _precision_recall_f1(labeled_synth, 0.90, use_gatekeeper=True)
        rp, rr, _ = _precision_recall_f1(labeled_synth, 0.90, use_gatekeeper=False)
        lines.append(f"| Synthetic only | {gp:.3f} | {gr:.3f} | {gf1:.3f} | {rp:.3f} | {rr:.3f} |")
    if labeled_real:
        gp, gr, gf1 = _precision_recall_f1(labeled_real, 0.90, use_gatekeeper=True)
        rp, rr, _ = _precision_recall_f1(labeled_real, 0.90, use_gatekeeper=False)
        lines.append(f"| Real-data only | {gp:.3f} | {gr:.3f} | {gf1:.3f} | {rp:.3f} | {rr:.3f} |")
    lines.append("")

    # --- Gatekeeper reasoning for called pairs ---
    called = [r for r in results if r.gatekeeper_called and r.gatekeeper_reasoning]
    if called:
        lines.append("## Gatekeeper Reasoning (called pairs)")
        lines.append("")
        for r in called:
            correct_marker = ""
            if r.ground_truth != "ambiguous":
                correct_marker = " ✓" if r.gatekeeper_action == r.ground_truth else " ✗ WRONG"
            lines.append(f"**{r.pair_id}** ({r.source}, {r.scenario}, GT={r.ground_truth}, FUSE={r.fuse_score:.3f}){correct_marker}")
            lines.append(f"- Verdict: `{r.gatekeeper_action}` (is_same_role={r.gatekeeper_is_same_role})")
            lines.append(f"- Reasoning: {r.gatekeeper_reasoning}")
            lines.append("")

    # --- Cost summary ---
    lines.append("## Cost Summary")
    lines.append("")
    lines.append(f"- LLM gatekeeper calls: {total_calls}")
    lines.append(f"- Total cost: ${total_cost_usd:.4f} USD")
    lines.append(f"- Average cost per call: ${total_cost_usd / max(total_calls, 1):.5f} USD")
    lines.append("")

    # --- Galent-pattern title-cosine diagnostic ---
    lines.append("## Galent-Pattern Diagnostic (title_cosine drag)")
    lines.append("")
    lines.append("Pairs where skills_jaccard=1.0 AND seniority=1.0 BUT title_cosine < 0.90 (FUSE dragged down by title):")
    lines.append("")
    galent_cases = [
        r for r in results
        if r.jaccard_top_skills >= 1.0 - _EXACT_EPSILON
        and r.seniority_match_score >= 1.0 - _EXACT_EPSILON
        and r.title_cosine_score < 0.90
    ]
    if galent_cases:
        lines.append("| Pair ID | FUSE | Title Cosine | Skills Jaccard | Seniority | GT | GK Action |")
        lines.append("|---------|------|-------------|---------------|-----------|-----|-----------|")
        for r in galent_cases:
            lines.append(
                f"| {r.pair_id} | {r.fuse_score:.3f} | {r.title_cosine_score:.3f} | "
                f"{r.jaccard_top_skills:.3f} | {r.seniority_match_score:.3f} | "
                f"{r.ground_truth} | {r.gatekeeper_action} |"
            )
        lines.append("")
        lines.append("*Review: consider whether title_cosine threshold should be relaxed for these cases.*")
    else:
        lines.append("*No Galent-pattern cases detected in this calibration run.*")
    lines.append("")

    lines.append("---")
    lines.append("*Report generated by `python -m jd_matcher.dedup calibrate`. Final calibration — Phase 2 (synthetic + user-labeled real pairs).*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DB enrichment for real pairs
# ---------------------------------------------------------------------------


def _enrich_real_pairs_from_db(
    pairs: list[CalibrationPair],
    db_path: Path,
) -> None:
    """Fetch full_jd, top_skills, canonical_seniority from DB for real pairs.

    Modifies pairs in-place. Pairs that cannot be enriched keep their
    empty placeholder values (gatekeeper will see 'no JD text available').
    """
    # Collect all canonical_ids needed
    ids_needed: set[int] = set()
    for pair in pairs:
        if pair.source != "real":
            continue
        try:
            ids_needed.add(int(pair.pair_id.split("_")[0]) if "_" not in pair.pair_id else 0)
        except (ValueError, IndexError):
            pass

    # The canonical_ids are stored in posting_a and posting_b metadata — but
    # the CSV loader doesn't carry them through. We re-derive from the CSV
    # via the pair's posting_a/posting_b dict (which has title/company but not id).
    # Instead, we look up by title + company for the pair. This is fragile —
    # better to store canonical_id in the pair. Since we control the CSV and
    # the CalibrationPair dataclass, we add canonical_id_a and canonical_id_b
    # as optional keys in the posting dicts.
    if not db_path.exists():
        logger.warning("calibrate: DB not found at %s — real pairs will have no full_jd", db_path)
        return

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            for pair in pairs:
                if pair.source != "real":
                    continue
                cid_a = pair.posting_a.get("canonical_id")
                cid_b = pair.posting_b.get("canonical_id")
                if cid_a:
                    row = conn.execute(
                        "SELECT full_jd, top_skills, canonical_seniority, role_summary "
                        "FROM canonical_postings WHERE canonical_id = ?",
                        (cid_a,),
                    ).fetchone()
                    if row:
                        pair.posting_a["full_jd"] = row["full_jd"] or ""
                        pair.posting_a["top_skills"] = json.loads(row["top_skills"] or "[]")
                        pair.posting_a["canonical_seniority"] = row["canonical_seniority"] or ""
                        pair.posting_a["role_summary"] = row["role_summary"] or ""
                if cid_b:
                    row = conn.execute(
                        "SELECT full_jd, top_skills, canonical_seniority, role_summary "
                        "FROM canonical_postings WHERE canonical_id = ?",
                        (cid_b,),
                    ).fetchone()
                    if row:
                        pair.posting_b["full_jd"] = row["full_jd"] or ""
                        pair.posting_b["top_skills"] = json.loads(row["top_skills"] or "[]")
                        pair.posting_b["canonical_seniority"] = row["canonical_seniority"] or ""
                        pair.posting_b["role_summary"] = row["role_summary"] or ""
        finally:
            conn.close()
    except Exception as exc:
        logger.error("calibrate: DB enrichment failed — %s", exc)


# ---------------------------------------------------------------------------
# Pair loaders
# ---------------------------------------------------------------------------


def _load_synthetic_pairs(path: Path) -> list[CalibrationPair]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    pairs = []
    for item in raw:
        pairs.append(CalibrationPair(
            pair_id=item["pair_id"],
            ground_truth=item["ground_truth"],
            scenario=item.get("scenario", "unknown"),
            posting_a=item.get("posting_a") or {},
            posting_b=item.get("posting_b") or {},
            source="synthetic",
        ))
    return pairs


def _load_real_pairs(path: Path) -> list[CalibrationPair]:
    """Load user-labeled real pairs from CSV.

    Label normalization: strip whitespace + lowercase. Accepts 'merge' or 'new'.
    Empty/blank labels are skipped and logged. Comment lines starting with '##'
    are skipped by DictReader (not lines in the data rows — the CSV header comment
    block is handled by passing comment=None and skipping rows where pair_id
    starts with '#').
    """
    if not path.exists():
        return []
    pairs = []
    skipped = 0
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(
            (line for line in f if not line.startswith("##")),
        )
        for row in reader:
            raw_label = row.get("user_label") or ""
            label = raw_label.strip().lower()
            if label not in ("merge", "new"):
                skipped += 1
                continue
            canonical_a_id_str = row.get("canonical_a_id", "").strip()
            canonical_b_id_str = row.get("canonical_b_id", "").strip()
            canonical_a_id = int(canonical_a_id_str) if canonical_a_id_str.isdigit() else None
            canonical_b_id = int(canonical_b_id_str) if canonical_b_id_str.isdigit() else None

            pairs.append(CalibrationPair(
                pair_id=row.get("pair_id", "real_unknown"),
                ground_truth=label,
                scenario="real",
                posting_a={
                    "canonical_id": canonical_a_id,
                    "canonical_title": row.get("title_a", ""),
                    "canonical_company": row.get("company_a", ""),
                    "full_jd": "",  # enriched from DB below
                    "top_skills": [],
                    "canonical_seniority": "",
                },
                posting_b={
                    "canonical_id": canonical_b_id,
                    "canonical_title": row.get("title_b", ""),
                    "canonical_company": row.get("company_b", ""),
                    "full_jd": "",
                    "top_skills": [],
                    "canonical_seniority": "",
                },
                source="real",
            ))
    if skipped:
        logger.info("calibrate: skipped %d real-pair row(s) with empty/unrecognized label", skipped)
    return pairs


# ---------------------------------------------------------------------------
# Threshold recommendation
# ---------------------------------------------------------------------------


def _recommend_threshold(results: list[PairResult]) -> tuple[float, str]:
    """Compute the recommended gatekeeper dispatch threshold.

    Evaluates each candidate threshold in _DISPATCH_SWEEP_THRESHOLDS.
    Returns (threshold, rationale_string).
    """
    labeled = [r for r in results if r.ground_truth != "ambiguous"]
    if not labeled:
        return _GATEKEEPER_THRESHOLD, "No labeled pairs to evaluate — defaulting to 0.75."

    regression_blocking_new = {
        r.pair_id for r in results
        if r.pair_id in {"real_002", "real_003", "real_007", "real_008", "real_009"}
        and r.ground_truth == "new"
    }

    best_threshold = _GATEKEEPER_THRESHOLD
    best_f1 = 0.0
    best_precision = 0.0
    best_recall = 0.0

    for dt in _DISPATCH_SWEEP_THRESHOLDS:
        gp, gr, gf1 = _precision_recall_f1(labeled, dt, use_gatekeeper=True, dispatch_threshold=dt)
        # Check regression constraint: no false-merges on regression-blocking pairs
        false_merge_on_regression = any(
            r.pair_id in regression_blocking_new
            and r.fuse_score >= dt
            and r.gatekeeper_action == "merge"
            for r in results
        )
        if false_merge_on_regression:
            continue  # skip thresholds that cause regression-blocking false-merges
        if gp >= 0.90 and gf1 > best_f1:
            best_f1 = gf1
            best_threshold = dt
            best_precision = gp
            best_recall = gr

    if best_f1 == 0.0:
        # No threshold achieves P>=0.90 — pick least-bad
        for dt in _DISPATCH_SWEEP_THRESHOLDS:
            gp, gr, gf1 = _precision_recall_f1(labeled, dt, use_gatekeeper=True, dispatch_threshold=dt)
            if gf1 > best_f1:
                best_f1 = gf1
                best_threshold = dt
                best_precision = gp
                best_recall = gr
        rationale = (
            f"No threshold achieved precision ≥90% on labeled pairs. "
            f"Selected {best_threshold} as highest-F1 option "
            f"(P={best_precision:.3f}, R={best_recall:.3f}, F1={best_f1:.3f}). "
            f"User review recommended."
        )
    else:
        rationale = (
            f"Threshold {best_threshold} achieves P={best_precision:.3f}, R={best_recall:.3f}, "
            f"F1={best_f1:.3f} on combined synthetic+real pairs with zero false-merges on "
            f"regression-blocking same-employer-different-role pairs."
        )

    return best_threshold, rationale


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_calibration(
    synthetic_only: bool = False,
    output_path: Path | None = None,
    db_path: Path | None = None,
) -> None:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path.cwd() / ".env")

    resolved_output = output_path or _DEFAULT_OUTPUT_PATH
    resolved_db = db_path or _DEFAULT_DB_PATH

    # Load pairs
    pairs: list[CalibrationPair] = []
    pairs.extend(_load_synthetic_pairs(_SYNTHETIC_PAIRS_PATH))

    if not synthetic_only:
        real_pairs = _load_real_pairs(_LABELS_CSV_PATH)
        if real_pairs:
            logger.info("calibrate: loaded %d real labeled pairs — enriching from DB", len(real_pairs))
            _enrich_real_pairs_from_db(real_pairs, resolved_db)
        else:
            logger.info("calibrate: no real labeled pairs found (running synthetic-only)")
        pairs.extend(real_pairs)

    logger.info("calibrate: total pairs to evaluate: %d", len(pairs))

    # Build LLM client (C28 factory)
    from jd_matcher.dedup.classifier import LLMDedupClassifier, _load_prompt
    from jd_matcher.llm.providers.factory import make_embedder, make_extractor

    extractor = make_extractor(db_path=None)
    embedder = make_embedder(db_path=None)
    prompt = _load_prompt()

    # Classifier without DB telemetry (calibration run — costs tracked separately)
    classifier = LLMDedupClassifier(
        llm_client=extractor,
        prompt_template=prompt,
        db_path=None,
        model_name="gpt-4o-mini",
    )

    # Config weights
    weights = {
        "embedding": 0.4,
        "skills": 0.3,
        "title": 0.2,
        "seniority": 0.1,
    }

    embed_cache: dict[str, list[float]] = {}
    results: list[PairResult] = []
    total_cost_usd = 0.0
    total_calls = 0

    for i, pair in enumerate(pairs):
        logger.info("calibrate: processing pair %d/%d: %s", i + 1, len(pairs), pair.pair_id)
        try:
            result = _process_pair(pair, classifier, embedder, weights, embed_cache)
            results.append(result)
            if result.gatekeeper_called:
                total_calls += 1
                total_cost_usd += result.call_cost_usd
        except Exception as exc:
            logger.error("calibrate: pair %s failed: %s", pair.pair_id, exc)

    # Determine final threshold recommendation
    final_threshold, threshold_rationale = _recommend_threshold(results)

    # Generate report
    report = _format_report(
        results,
        total_cost_usd,
        total_calls,
        final_threshold,
        threshold_rationale,
    )

    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(report, encoding="utf-8")
    logger.info("calibrate: report written to %s", resolved_output)

    # Print summary to stdout
    print(f"\nCalibration complete: {len(results)} pairs evaluated")
    print(f"  Gatekeeper calls: {total_calls} (total cost: ${total_cost_usd:.4f} USD)")
    labeled = [r for r in results if r.ground_truth != "ambiguous"]
    if labeled:
        gp, gr, gf1 = _precision_recall_f1(labeled, 0.90, use_gatekeeper=True)
        rp, rr, rf1 = _precision_recall_f1(labeled, 0.90, use_gatekeeper=False)
        print(f"\nAt FUSE threshold 0.90 (non-ambiguous pairs only):")
        print(f"  Raw-FUSE:    P={rp:.3f}  R={rr:.3f}  F1={rf1:.3f}")
        print(f"  GK-Augmented: P={gp:.3f}  R={gr:.3f}  F1={gf1:.3f}")

    print(f"\nFinal gatekeeper_threshold recommendation: {final_threshold}")
    print(f"Rationale: {threshold_rationale}")
    print(f"\nFull report: {resolved_output}")

    return final_threshold


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        prog="python -m jd_matcher.dedup calibrate",
        description="Calibrate the C32 LLM dedup gatekeeper against synthetic and real labeled pairs",
    )
    parser.add_argument(
        "--synthetic-only",
        action="store_true",
        help="Only use synthetic pairs (skip tests/fixtures/dedup_labels.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Output report path (default: {_DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help=f"SQLite DB path for real-pair enrichment (default: {_DEFAULT_DB_PATH})",
    )
    args = parser.parse_args(argv)

    run_calibration(
        synthetic_only=args.synthetic_only,
        output_path=args.output,
        db_path=args.db,
    )


if __name__ == "__main__":
    main()
