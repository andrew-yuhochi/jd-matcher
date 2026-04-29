"""Unit tests for scripts/analyze_top_skills.py (Phase A, TASK-M2-006b).

Uses an in-memory SQLite fixture — no live DB required.
Run with: SKIP_LIVE=1 python -m pytest tests/scripts/test_analyze_top_skills.py -v
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

# Make the scripts/ directory importable
_PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from analyze_top_skills import (  # noqa: E402
    _normalize,
    build_clusters,
    load_skill_strings,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def in_memory_db(tmp_path) -> Path:
    """Create a minimal jd-matcher schema with synthetic extraction_cache rows."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE users (
            id TEXT PRIMARY KEY
        );
        INSERT INTO users VALUES ('default');

        CREATE TABLE extraction_cache (
            text_hash                  TEXT NOT NULL,
            model_name                 TEXT NOT NULL,
            user_id                    TEXT NOT NULL DEFAULT 'default',
            canonical_extraction_json  TEXT NOT NULL,
            cached_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (text_hash, model_name)
        );
        """
    )

    rows = [
        # Posting 1: uses "ML" and "Python"
        {
            "text_hash": "hash1",
            "extraction": {
                "top_skills": ["ML", "Python", "SQL"]
            },
        },
        # Posting 2: uses "Machine Learning" (same concept as ML) and "python " (trailing space)
        {
            "text_hash": "hash2",
            "extraction": {
                "top_skills": ["Machine Learning", "python ", "Data Engineering"]
            },
        },
        # Posting 3: uses "machine learning" lowercase + "Python" again
        {
            "text_hash": "hash3",
            "extraction": {
                "top_skills": ["machine learning", "Python", "SQL"]
            },
        },
        # Posting 4: a completely unique skill (single-form)
        {
            "text_hash": "hash4",
            "extraction": {
                "top_skills": ["Kubernetes", "Python"]
            },
        },
    ]

    for row in rows:
        conn.execute(
            "INSERT INTO extraction_cache (text_hash, model_name, canonical_extraction_json) "
            "VALUES (?, ?, ?)",
            (row["text_hash"], "gpt-4o-mini", json.dumps(row["extraction"])),
        )
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Test 1: normalization (case + whitespace)
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_lowercase(self):
        assert _normalize("Machine Learning") == "machine learning"

    def test_abbreviation_unchanged(self):
        assert _normalize("ML") == "ml"

    def test_strips_leading_trailing_whitespace(self):
        assert _normalize("  Python  ") == "python"

    def test_collapses_internal_whitespace(self):
        assert _normalize("A/B  Testing") == "a/b  testing".replace("  ", " ")
        assert _normalize("Data   Engineering") == "data engineering"

    def test_already_normalized_unchanged(self):
        assert _normalize("python") == "python"


# ---------------------------------------------------------------------------
# Test 2: cluster grouping — ML / Machine Learning / machine learning → one cluster
# ---------------------------------------------------------------------------

class TestBuildClusters:
    def test_ml_variants_group_into_one_cluster(self):
        raw = ["ML", "Machine Learning", "machine learning", "Machine Learning"]
        clusters = build_clusters(raw)
        # All three normalize to different strings ("ml", "machine learning")
        # "ML" → "ml", "Machine Learning" → "machine learning",
        # "machine learning" → "machine learning"
        # So two clusters: "ml" and "machine learning"
        assert "ml" in clusters
        assert "machine learning" in clusters
        assert clusters["machine learning"]["Machine Learning"] == 2
        assert clusters["machine learning"]["machine learning"] == 1

    def test_python_with_trailing_space_merges(self):
        raw = ["Python", "python ", "Python"]
        clusters = build_clusters(raw)
        # Both normalize to "python"
        assert "python" in clusters
        assert len(clusters) == 1
        assert clusters["python"]["Python"] == 2
        assert clusters["python"]["python "] == 1

    def test_unique_skills_form_own_clusters(self):
        raw = ["Kubernetes", "SQL", "Airflow"]
        clusters = build_clusters(raw)
        assert len(clusters) == 3
        for norm in ("kubernetes", "sql", "airflow"):
            assert norm in clusters

    def test_empty_input_returns_empty(self):
        assert build_clusters([]) == {}


# ---------------------------------------------------------------------------
# Test 3: multi-variant filter — single-form clusters excluded
# ---------------------------------------------------------------------------

class TestMultiVariantFilter:
    def test_single_form_clusters_excluded(self):
        raw = ["Python", "Python", "ML", "Machine Learning"]
        clusters = build_clusters(raw)
        multi = {
            norm: surfaces
            for norm, surfaces in clusters.items()
            if len(surfaces) >= 2
        }
        single = {
            norm: surfaces
            for norm, surfaces in clusters.items()
            if len(surfaces) < 2
        }
        # "python" has only one surface form → single
        assert "python" in single
        assert "python" not in multi
        # "ml" and "machine learning" each have one surface form too
        # (they're different normalized forms!) → both single
        assert "ml" in single
        assert "machine learning" in single

    def test_multi_variant_detected(self):
        # "Python" and "python " both normalize to "python"
        raw = ["Python", "python ", "SQL"]
        clusters = build_clusters(raw)
        multi = {
            norm: surfaces
            for norm, surfaces in clusters.items()
            if len(surfaces) >= 2
        }
        assert "python" in multi
        assert "sql" not in multi

    def test_load_skill_strings_from_fixture(self, in_memory_db):
        skills, row_count = load_skill_strings(in_memory_db)
        assert row_count == 4
        # 3 + 3 + 3 + 2 = 11 total mentions
        assert len(skills) == 11
        assert "ML" in skills
        assert "Machine Learning" in skills
        assert "machine learning" in skills
