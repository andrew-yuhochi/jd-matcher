"""Phase E synthetic regression tests for TASK-M2-006b — canonical taxonomy enforcement.

Five hand-crafted JDs with known canonical-skill mappings. Each test verifies that
the updated canonical_extraction_v1.txt prompt correctly:
  - Maps skill variants to the canonical form
  - Excludes soft skills from top_skills

Run live:
    SKIP_LIVE=0 .venv/bin/python -m pytest tests/llm/test_canonical_skills_regression.py -v

Estimated cost: ~$0.005 per test × 5 = ~$0.025 total
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.llm.extract import PostingRow, extract_canonical

SKIP_LIVE = os.environ.get("SKIP_LIVE", "1") == "1"

# ---------------------------------------------------------------------------
# Synthetic JD fixtures
# ---------------------------------------------------------------------------

# JD 1: ML and machine learning → exactly one "Machine Learning"
_JD1 = """\
Senior Data Scientist — Acme Corp (Vancouver, BC)

We are looking for a Data Scientist with strong experience in ML and machine
learning. You will build predictive models using Python and SQL to support
our growth analytics team. Experience with A/B Testing and Data Analysis is
expected.
"""

# JD 2: PySpark and Apache Spark → "Spark" (single entry)
_JD2 = """\
Data Engineer — Streamy Inc (Toronto, ON)

Join our data platform team to build large-scale pipelines using PySpark and
Apache Spark for ETL. You will also work with AWS and SQL to power our
real-time data infrastructure. Python experience required.
"""

# JD 3: Pytorch, tensorflow, scikit-learn → "PyTorch", "TensorFlow", "Scikit-Learn"
_JD3 = """\
Machine Learning Engineer — NeuroTech Labs (Montreal, QC)

We need an ML engineer with hands-on experience in deep learning frameworks:
Pytorch, tensorflow, and scikit-learn. You will design and train Deep Learning
models using Python. Prior experience with PyTorch is a strong plus.
"""

# JD 4: communication, collaboration, problem-solving, NLP → only "NLP" in top_skills
_JD4 = """\
NLP Research Scientist — Lingua AI (Remote — Canada)

We are seeking a Research Scientist with expertise in Natural Language
Processing. Strong communication and collaboration skills are essential.
You should also have excellent problem-solving abilities. The role requires
deep knowledge of NLP, LLMs, and Python.
"""

# JD 5: GenAI, LLMs, large language models → "Generative AI" + "LLMs" (kept separate)
_JD5 = """\
Generative AI Engineer — FutureStack (Vancouver, BC)

Build and deploy GenAI systems using LLMs and large language models. You will
work with the latest Generative AI frameworks, fine-tune LLMs for domain-specific
tasks, and integrate these models into production systems. Python and MLOps
experience required.
"""

# ---------------------------------------------------------------------------
# Live test class
# ---------------------------------------------------------------------------


@pytest.mark.skipif(SKIP_LIVE, reason="SKIP_LIVE=1 — set SKIP_LIVE=0 to run live tests")
class TestCanonicalSkillsRegression:
    """Verify that the 43-entry canonical taxonomy prompt maps skill variants correctly.

    Each test uses a temporary SQLite DB so it doesn't mutate the real jd-matcher.db.
    Cache is not busted between tests — a fresh temp DB starts empty.
    """

    @pytest.fixture(autouse=True)
    def temp_db(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        self._db_path = db_path

    def _extract(self, jd_text: str, posting_id: int = 1) -> list[str]:
        posting = PostingRow(id=posting_id, full_jd=jd_text)
        result = extract_canonical(posting, db_path=self._db_path)
        return result.top_skills

    # -----------------------------------------------------------------------

    def test_jd1_ml_variants_collapse_to_machine_learning(self):
        """JD mentions 'ML and machine learning' → 'Machine Learning' appears exactly once."""
        skills = self._extract(_JD1, posting_id=1)
        ml_hits = [s for s in skills if s == "Machine Learning"]
        assert len(ml_hits) == 1, (
            f"Expected exactly one 'Machine Learning' entry; got {ml_hits} in: {skills}"
        )

    def test_jd2_pyspark_apache_spark_collapse_to_spark(self):
        """JD mentions 'PySpark and Apache Spark' → 'Spark' (single entry, not both)."""
        skills = self._extract(_JD2, posting_id=2)
        spark_hits = [s for s in skills if s == "Spark"]
        bad_hits = [s for s in skills if s in ("PySpark", "Apache Spark")]
        assert len(spark_hits) == 1, (
            f"Expected exactly one 'Spark'; got spark_hits={spark_hits} in: {skills}"
        )
        assert len(bad_hits) == 0, (
            f"'PySpark' or 'Apache Spark' should not appear; found: {bad_hits} in: {skills}"
        )

    def test_jd3_framework_capitalization_canonical(self):
        """JD mentions 'Pytorch, tensorflow, scikit-learn' → canonical spellings enforced."""
        skills = self._extract(_JD3, posting_id=3)
        assert "PyTorch" in skills, f"Expected 'PyTorch'; skills={skills}"
        assert "TensorFlow" in skills, f"Expected 'TensorFlow'; skills={skills}"
        assert "Scikit-Learn" in skills, f"Expected 'Scikit-Learn'; skills={skills}"
        # Reject non-canonical spellings
        bad = [s for s in skills if s.lower() in ("pytorch", "tensorflow", "scikit-learn") and s not in ("PyTorch", "TensorFlow", "Scikit-Learn")]
        assert bad == [], f"Non-canonical framework spellings found: {bad}"

    def test_jd4_soft_skills_excluded_nlp_retained(self):
        """JD mentions communication/collaboration/problem-solving + NLP → only NLP in top_skills."""
        skills = self._extract(_JD4, posting_id=4)
        soft_in_skills = [
            s for s in skills
            if s.lower() in ("communication", "collaboration", "problem-solving", "problem solving")
        ]
        assert soft_in_skills == [], (
            f"Soft skills should be excluded; found: {soft_in_skills} in: {skills}"
        )
        assert "NLP" in skills, f"Expected 'NLP' in top_skills; got: {skills}"

    def test_jd5_genai_llms_kept_separate(self):
        """JD mentions 'GenAI, LLMs, large language models' → 'Generative AI' + 'LLMs' separate."""
        skills = self._extract(_JD5, posting_id=5)
        assert "Generative AI" in skills, f"Expected 'Generative AI'; skills={skills}"
        assert "LLMs" in skills, f"Expected 'LLMs'; skills={skills}"
        # GenAI should map to Generative AI; not remain as "GenAI"
        bad = [s for s in skills if s == "GenAI"]
        assert bad == [], f"'GenAI' should map to 'Generative AI'; found raw 'GenAI' in: {skills}"
