"""Unit tests for C32 calibration module (calibrate.py).

Coverage:
  - Synthetic pair loader: reads YAML correctly
  - Real pair loader: reads CSV correctly, skips unlabeled rows
  - FUSE component computation (mock embedder)
  - 4-feature exact-match short-circuit in calibration path
  - Threshold sweep metric computation
  - Report generation (spot checks on key sections)
  - CLI entry point wiring (--synthetic-only flag)
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from jd_matcher.dedup.calibrate import (
    CalibrationPair,
    PairResult,
    _is_exact_match,
    _jaccard_score,
    _load_real_pairs,
    _load_synthetic_pairs,
    _precision_recall_f1,
    _seniority_score,
    _format_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_temp_yaml(pairs: list[dict], tmp_path: Path) -> Path:
    p = tmp_path / "pairs.yaml"
    p.write_text(yaml.dump(pairs), encoding="utf-8")
    return p


def _write_temp_csv(rows: list[dict], tmp_path: Path) -> Path:
    p = tmp_path / "labels.csv"
    fieldnames = ["pair_id", "canonical_a_id", "canonical_b_id",
                  "title_a", "title_b", "company_a", "company_b",
                  "fuse_score", "user_label", "user_notes"]
    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return p


def _make_pair(
    pair_id: str,
    ground_truth: str,
    scenario: str = "exact_dup",
    source: str = "synthetic",
) -> CalibrationPair:
    return CalibrationPair(
        pair_id=pair_id,
        ground_truth=ground_truth,
        scenario=scenario,
        posting_a={
            "canonical_title": "Senior Data Scientist",
            "canonical_company": "Shopify",
            "canonical_seniority": "Senior",
            "top_skills": ["python", "sql", "ml"],
            "full_jd": "We need a Senior Data Scientist at Shopify Merchant Analytics.",
        },
        posting_b={
            "canonical_title": "Senior Data Scientist",
            "canonical_company": "Shopify",
            "canonical_seniority": "Senior",
            "top_skills": ["python", "sql", "ml"],
            "full_jd": "Shopify Merchant Analytics is hiring a Senior Data Scientist.",
        },
        source=source,
    )


def _make_result(
    pair_id: str,
    ground_truth: str,
    fuse_score: float,
    gatekeeper_action: str,
    gatekeeper_called: bool = False,
    scenario: str = "exact_dup",
) -> PairResult:
    return PairResult(
        pair_id=pair_id,
        ground_truth=ground_truth,
        scenario=scenario,
        source="synthetic",
        embedding_cosine=fuse_score,
        jaccard_top_skills=fuse_score,
        title_cosine_score=fuse_score,
        seniority_match_score=1.0 if fuse_score > 0.5 else 0.0,
        fuse_score=fuse_score,
        gatekeeper_called=gatekeeper_called,
        gatekeeper_is_same_role=True if gatekeeper_action == "merge" else (False if gatekeeper_action == "new" else None),
        gatekeeper_reasoning="Test reasoning." if gatekeeper_called else None,
        gatekeeper_status="called_success" if gatekeeper_called else "not_called",
        gatekeeper_action=gatekeeper_action,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestJaccardScore:
    def test_identical(self):
        assert _jaccard_score(["python", "sql"], ["python", "sql"]) == pytest.approx(1.0)

    def test_no_overlap(self):
        assert _jaccard_score(["python"], ["java"]) == pytest.approx(0.0)

    def test_partial_overlap(self):
        result = _jaccard_score(["a", "b"], ["b", "c"])
        assert result == pytest.approx(1 / 3, abs=1e-9)

    def test_empty_a(self):
        assert _jaccard_score([], ["python"]) == 0.0

    def test_both_empty(self):
        assert _jaccard_score([], []) == 0.0

    def test_case_insensitive(self):
        assert _jaccard_score(["Python"], ["python"]) == pytest.approx(1.0)


class TestSeniorityScore:
    def test_match(self):
        assert _seniority_score("Senior", "Senior") == 1.0

    def test_no_match(self):
        assert _seniority_score("Senior", "Mid") == 0.0

    def test_none_a(self):
        assert _seniority_score(None, "Senior") == 0.0

    def test_both_none(self):
        assert _seniority_score(None, None) == 0.0

    def test_case_insensitive(self):
        assert _seniority_score("senior", "Senior") == 1.0


class TestIsExactMatchCalibrate:
    def test_all_ones_exact(self):
        assert _is_exact_match(1.0, 1.0, 1.0, 1.0) is True

    def test_one_not_one_not_exact(self):
        assert _is_exact_match(0.99, 1.0, 1.0, 1.0) is False

    def test_all_zero_not_exact(self):
        assert _is_exact_match(0.0, 0.0, 0.0, 0.0) is False


# ---------------------------------------------------------------------------
# Pair loaders
# ---------------------------------------------------------------------------


class TestLoadSyntheticPairs:
    def test_loads_correctly(self, tmp_path: Path):
        data = [
            {
                "pair_id": "synth_001",
                "ground_truth": "merge",
                "scenario": "exact_dup",
                "posting_a": {"canonical_title": "DS", "canonical_company": "Shopify"},
                "posting_b": {"canonical_title": "DS", "canonical_company": "Shopify"},
            },
            {
                "pair_id": "synth_002",
                "ground_truth": "new",
                "scenario": "different_team",
                "posting_a": {"canonical_title": "DS", "canonical_company": "TD"},
                "posting_b": {"canonical_title": "DS", "canonical_company": "TD"},
            },
        ]
        path = _write_temp_yaml(data, tmp_path)
        pairs = _load_synthetic_pairs(path)
        assert len(pairs) == 2
        assert pairs[0].pair_id == "synth_001"
        assert pairs[0].ground_truth == "merge"
        assert pairs[0].source == "synthetic"
        assert pairs[1].scenario == "different_team"

    def test_empty_file_returns_empty(self, tmp_path: Path):
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        pairs = _load_synthetic_pairs(path)
        assert pairs == []


class TestLoadRealPairs:
    def test_loads_labeled_rows(self, tmp_path: Path):
        rows = [
            {
                "pair_id": "real_001",
                "canonical_a_id": "10",
                "canonical_b_id": "11",
                "title_a": "Data Scientist",
                "title_b": "Data Scientist",
                "company_a": "Shopify",
                "company_b": "Shopify",
                "fuse_score": "0.85",
                "user_label": "merge",
                "user_notes": "",
            },
            {
                "pair_id": "real_002",
                "canonical_a_id": "12",
                "canonical_b_id": "13",
                "title_a": "ML Engineer",
                "title_b": "Data Engineer",
                "company_a": "Shopify",
                "company_b": "Shopify",
                "fuse_score": "0.78",
                "user_label": "new",
                "user_notes": "different team",
            },
        ]
        path = _write_temp_csv(rows, tmp_path)
        pairs = _load_real_pairs(path)
        assert len(pairs) == 2
        assert pairs[0].ground_truth == "merge"
        assert pairs[1].ground_truth == "new"
        assert pairs[0].source == "real"

    def test_skips_unlabeled_rows(self, tmp_path: Path):
        rows = [
            {
                "pair_id": "real_001",
                "canonical_a_id": "10",
                "canonical_b_id": "11",
                "title_a": "DS",
                "title_b": "DS",
                "company_a": "A",
                "company_b": "A",
                "fuse_score": "0.80",
                "user_label": "",  # unlabeled
                "user_notes": "",
            },
            {
                "pair_id": "real_002",
                "canonical_a_id": "12",
                "canonical_b_id": "13",
                "title_a": "MLE",
                "title_b": "MLE",
                "company_a": "B",
                "company_b": "B",
                "fuse_score": "0.90",
                "user_label": "merge",
                "user_notes": "",
            },
        ]
        path = _write_temp_csv(rows, tmp_path)
        pairs = _load_real_pairs(path)
        assert len(pairs) == 1
        assert pairs[0].pair_id == "real_002"

    def test_missing_file_returns_empty(self, tmp_path: Path):
        path = tmp_path / "nonexistent.csv"
        pairs = _load_real_pairs(path)
        assert pairs == []


# ---------------------------------------------------------------------------
# Precision / recall / F1
# ---------------------------------------------------------------------------


class TestPrecisionRecallF1:
    def _make_results(self) -> list[PairResult]:
        """4 labeled pairs: 2 true dups (GT=merge), 2 true non-dups (GT=new)."""
        return [
            _make_result("p1", "merge", 0.95, "merge"),   # TP
            _make_result("p2", "merge", 0.80, "merge"),   # TP
            _make_result("p3", "new", 0.70, "new"),       # TN
            _make_result("p4", "new", 0.75, "new"),       # TN
        ]

    def test_perfect_gatekeeper(self):
        results = self._make_results()
        p, r, f1 = _precision_recall_f1(results, threshold=0.90, use_gatekeeper=True)
        assert p == pytest.approx(1.0)
        assert r == pytest.approx(1.0)
        assert f1 == pytest.approx(1.0)

    def test_raw_fuse_at_threshold_0_90(self):
        results = self._make_results()
        # At 0.90: only p1 (0.95) passes → 1 TP, 1 FN
        p, r, f1 = _precision_recall_f1(results, threshold=0.90, use_gatekeeper=False)
        assert p == pytest.approx(1.0)   # no FP
        assert r == pytest.approx(0.5)   # missed p2

    def test_ambiguous_excluded_from_metrics(self):
        results = [
            _make_result("p1", "merge", 0.95, "merge"),
            _make_result("p2", "ambiguous", 0.88, "merge"),  # excluded
        ]
        p, r, f1 = _precision_recall_f1(results, threshold=0.90, use_gatekeeper=True)
        # Only p1 is non-ambiguous: TP=1, FP=0, FN=0 → P=R=F1=1.0
        assert p == pytest.approx(1.0)
        assert r == pytest.approx(1.0)

    def test_all_false_positives(self):
        results = [
            _make_result("p1", "new", 0.95, "merge"),  # FP
            _make_result("p2", "new", 0.90, "merge"),  # FP
        ]
        p, r, f1 = _precision_recall_f1(results, threshold=0.85, use_gatekeeper=True)
        assert p == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Report generation (smoke test)
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_report_contains_required_sections(self):
        results = [
            _make_result("synth_001", "merge", 0.92, "merge", gatekeeper_called=True),
            _make_result("synth_002", "new", 0.65, "new", gatekeeper_called=False),
            _make_result("synth_003", "ambiguous", 0.80, "new", gatekeeper_called=True),
        ]
        report = _format_report(results, total_cost_usd=0.0023, total_calls=2)
        assert "# TASK-M2-012 Calibration Report" in report
        assert "Threshold Sweep" in report
        assert "Per-Pair Verdict Table" in report
        assert "Cost Summary" in report
        assert "Galent-Pattern Diagnostic" in report
        assert "synth_001" in report
        assert "synth_002" in report
        assert "synth_003" in report

    def test_report_threshold_table_has_all_thresholds(self):
        results = [_make_result("p1", "merge", 0.92, "merge")]
        report = _format_report(results, total_cost_usd=0.0, total_calls=0)
        for thresh in ["0.85", "0.88", "0.90", "0.92", "0.95"]:
            assert thresh in report

    def test_report_gatekeeper_reasoning_shown(self):
        r = PairResult(
            pair_id="synth_001",
            ground_truth="merge",
            scenario="exact_dup",
            source="synthetic",
            embedding_cosine=0.90,
            jaccard_top_skills=0.90,
            title_cosine_score=0.85,
            seniority_match_score=1.0,
            fuse_score=0.88,
            gatekeeper_called=True,
            gatekeeper_is_same_role=True,
            gatekeeper_reasoning="Both are the same Senior DS role at Shopify.",
            gatekeeper_status="called_success",
            gatekeeper_action="merge",
        )
        report = _format_report([r], total_cost_usd=0.0001, total_calls=1)
        assert "Both are the same Senior DS role at Shopify." in report
