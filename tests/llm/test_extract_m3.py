"""Tests for TASK-M3-002 — C18 v2 prompt + Pydantic extension + cache key bump.

Coverage:
  - v2 prompt file exists and contains required field sections (AC #1)
  - CanonicalExtraction has all 9 new M3 fields with correct types (AC #2)
  - Pydantic rejects invalid M3 enum values (AC #2)
  - Cache key is now a 3-tuple (text_hash, model_name, prompt_version) (AC #3)
  - v1 cache entries do NOT satisfy v2 lookups (AC #3 — load-bearing)
  - Industry Literal matches the 16-sector list verbatim (AC #5)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.llm.extract import (
    CanonicalExtraction,
    ExtractionParseError,
    PostingRow,
    _PROCESS_CACHE,
    _PROMPT_VERSION,
    _db_cache_get,
    _db_cache_put,
    _INDUSTRY_VALUES,
    _ROLE_ORIENTATION_VALUES,
    extract_canonical,
)
from jd_matcher.llm.providers.base import ExtractionMetadata

pytestmark = pytest.mark.slow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_META = ExtractionMetadata(
    input_tokens=800, output_tokens=300, latency_ms=1200, cost_usd=0.00025
)

_VALID_V2_JSON = json.dumps(
    {
        "canonical_title": "Senior Data Scientist",
        "canonical_company": "Shopify",
        "canonical_seniority": "Senior",
        "canonical_location": "Remote — Canada",
        "team_or_department": "Data Platform",
        "top_skills": ["Python", "Machine Learning", "SQL"],
        "role_summary": (
            "A senior data science role focused on building production ML models. "
            "The team works on data platform infrastructure and analytics tooling. "
            "Core skills include Python, SQL, and distributed computing."
        ),
        "fit_score": 5,
        "fit_reasoning": "Core duties are building production ML models — pure DS work.",
        "industry": "B2B SaaS",
        "role_orientation": ["Problem-Solving", "Engineering"],
        "salary_min_cad": 130000,
        "salary_max_cad": 160000,
        "citizenship_requirement": "not_mentioned",
        "citizenship_reason": "",
        "can_hire_in_canada": "yes",
    }
)


def _make_v2_provider(return_json: str = _VALID_V2_JSON):
    from unittest.mock import MagicMock

    p = MagicMock()
    p.extract.return_value = (return_json, _MOCK_META)
    return p


def _make_posting(
    posting_id: int = 1,
    full_jd: str = "A Shopify job for a Senior Data Scientist in Canada.",
) -> PostingRow:
    return PostingRow(id=posting_id, full_jd=full_jd)


@pytest.fixture(autouse=True)
def clear_process_cache():
    _PROCESS_CACHE.clear()
    yield
    _PROCESS_CACHE.clear()


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_m3_002.db"
    init_db(db)
    return db


# ---------------------------------------------------------------------------
# AC #1 — v2 prompt file exists with required sections
# ---------------------------------------------------------------------------


class TestPromptFileV2:
    def test_prompt_file_exists(self):
        project_root = Path(__file__).parents[2]
        prompt_path = project_root / "prompts" / "canonical_extraction_v2.txt"
        assert prompt_path.exists(), f"v2 prompt not found at {prompt_path}"

    def test_prompt_version_constant_is_v2(self):
        assert _PROMPT_VERSION == "v2"

    def test_prompt_contains_fit_score_section(self):
        project_root = Path(__file__).parents[2]
        content = (project_root / "prompts" / "canonical_extraction_v2.txt").read_text()
        assert "FIT SCORE" in content

    def test_prompt_contains_fit_reasoning_section(self):
        project_root = Path(__file__).parents[2]
        content = (project_root / "prompts" / "canonical_extraction_v2.txt").read_text()
        assert "FIT REASONING" in content

    def test_prompt_contains_industry_section(self):
        project_root = Path(__file__).parents[2]
        content = (project_root / "prompts" / "canonical_extraction_v2.txt").read_text()
        assert "INDUSTRY" in content

    def test_prompt_contains_role_orientation_section(self):
        project_root = Path(__file__).parents[2]
        content = (project_root / "prompts" / "canonical_extraction_v2.txt").read_text()
        assert "ROLE ORIENTATION" in content

    def test_prompt_contains_salary_section(self):
        project_root = Path(__file__).parents[2]
        content = (project_root / "prompts" / "canonical_extraction_v2.txt").read_text()
        assert "SALARY" in content

    def test_prompt_contains_citizenship_section(self):
        project_root = Path(__file__).parents[2]
        content = (project_root / "prompts" / "canonical_extraction_v2.txt").read_text()
        assert "CITIZENSHIP" in content

    def test_prompt_contains_can_hire_section(self):
        project_root = Path(__file__).parents[2]
        content = (project_root / "prompts" / "canonical_extraction_v2.txt").read_text()
        assert "CAN HIRE IN CANADA" in content

    def test_prompt_json_schema_has_all_new_fields(self):
        project_root = Path(__file__).parents[2]
        content = (project_root / "prompts" / "canonical_extraction_v2.txt").read_text()
        for field in [
            "fit_score",
            "fit_reasoning",
            "industry",
            "role_orientation",
            "salary_min_cad",
            "salary_max_cad",
            "citizenship_requirement",
            "citizenship_reason",
            "can_hire_in_canada",
        ]:
            assert field in content, f"Field '{field}' missing from v2 prompt schema"


# ---------------------------------------------------------------------------
# AC #2 — Pydantic model has all 9 new fields + correct constraints
# ---------------------------------------------------------------------------


class TestCanonicalExtractionV2Model:
    def _base_kwargs(self) -> dict:
        return {
            "canonical_title": "Senior Data Scientist",
            "canonical_company": "Shopify",
            "canonical_seniority": "Senior",
            "canonical_location": "Vancouver",
            "top_skills": ["Python"],
            "role_summary": "A role.",
            "fit_score": 5,
            "fit_reasoning": "Core DS role.",
            "industry": "B2B SaaS",
            "role_orientation": ["Problem-Solving"],
            "citizenship_requirement": "not_mentioned",
            "citizenship_reason": "",
            "can_hire_in_canada": "yes",
        }

    def test_valid_full_v2_model_accepted(self):
        m = CanonicalExtraction(**self._base_kwargs())
        assert m.fit_score == 5
        assert m.industry == "B2B SaaS"
        assert m.role_orientation == ["Problem-Solving"]
        assert m.citizenship_requirement == "not_mentioned"
        assert m.can_hire_in_canada == "yes"

    def test_fit_score_range_1_to_5_all_valid(self):
        for score in range(1, 6):
            m = CanonicalExtraction(**{**self._base_kwargs(), "fit_score": score})
            assert m.fit_score == score

    def test_fit_score_0_rejected(self):
        with pytest.raises(Exception):
            CanonicalExtraction(**{**self._base_kwargs(), "fit_score": 0})

    def test_fit_score_6_rejected(self):
        with pytest.raises(Exception):
            CanonicalExtraction(**{**self._base_kwargs(), "fit_score": 6})

    def test_all_16_industry_values_accepted(self):
        from jd_matcher.llm.extract import _INDUSTRY_VALUES

        for industry in _INDUSTRY_VALUES:
            m = CanonicalExtraction(**{**self._base_kwargs(), "industry": industry})
            assert m.industry == industry

    def test_invalid_industry_rejected(self):
        with pytest.raises(Exception):
            CanonicalExtraction(**{**self._base_kwargs(), "industry": "Finance"})

    def test_role_orientation_all_three_values_valid(self):
        m = CanonicalExtraction(
            **{
                **self._base_kwargs(),
                "role_orientation": ["Engineering", "Problem-Solving", "Communication"],
            }
        )
        assert len(m.role_orientation) == 3

    def test_role_orientation_empty_list_rejected(self):
        with pytest.raises(Exception):
            CanonicalExtraction(**{**self._base_kwargs(), "role_orientation": []})

    def test_role_orientation_invalid_value_rejected(self):
        with pytest.raises(Exception):
            CanonicalExtraction(
                **{**self._base_kwargs(), "role_orientation": ["Research"]}
            )

    def test_role_orientation_four_items_rejected(self):
        with pytest.raises(Exception):
            CanonicalExtraction(
                **{
                    **self._base_kwargs(),
                    "role_orientation": [
                        "Engineering",
                        "Problem-Solving",
                        "Communication",
                        "Engineering",
                    ],
                }
            )

    def test_salary_nullable(self):
        m = CanonicalExtraction(**self._base_kwargs())
        assert m.salary_min_cad is None
        assert m.salary_max_cad is None

    def test_salary_integers_accepted(self):
        m = CanonicalExtraction(
            **{**self._base_kwargs(), "salary_min_cad": 95000, "salary_max_cad": 130000}
        )
        assert m.salary_min_cad == 95000
        assert m.salary_max_cad == 130000

    def test_citizenship_requirement_all_values_valid(self):
        for val in ["required", "preferred", "not_mentioned"]:
            m = CanonicalExtraction(
                **{**self._base_kwargs(), "citizenship_requirement": val}
            )
            assert m.citizenship_requirement == val

    def test_citizenship_requirement_invalid_rejected(self):
        with pytest.raises(Exception):
            CanonicalExtraction(
                **{**self._base_kwargs(), "citizenship_requirement": "unknown"}
            )

    def test_can_hire_in_canada_all_values_valid(self):
        for val in ["yes", "likely", "no", "unclear"]:
            m = CanonicalExtraction(
                **{**self._base_kwargs(), "can_hire_in_canada": val}
            )
            assert m.can_hire_in_canada == val

    def test_can_hire_in_canada_invalid_rejected(self):
        with pytest.raises(Exception):
            CanonicalExtraction(
                **{**self._base_kwargs(), "can_hire_in_canada": "maybe"}
            )

    def test_citizenship_reason_empty_string_valid(self):
        m = CanonicalExtraction(
            **{
                **self._base_kwargs(),
                "citizenship_requirement": "not_mentioned",
                "citizenship_reason": "",
            }
        )
        assert m.citizenship_reason == ""

    def test_citizenship_reason_filled_when_required(self):
        m = CanonicalExtraction(
            **{
                **self._base_kwargs(),
                "citizenship_requirement": "required",
                "citizenship_reason": "Secret clearance requires Canadian citizenship.",
            }
        )
        assert "clearance" in m.citizenship_reason


# ---------------------------------------------------------------------------
# AC #3 — Cache key includes prompt_version (3-tuple)
# ---------------------------------------------------------------------------


class TestCacheKeyV2:
    def test_process_cache_is_keyed_by_three_tuple(self, tmp_db):
        """Successful extraction stores a (text_hash, model_name, prompt_version) key."""
        posting = _make_posting()
        provider = _make_v2_provider()
        extract_canonical(posting, provider=provider, db_path=tmp_db)
        assert len(_PROCESS_CACHE) == 1
        key = next(iter(_PROCESS_CACHE.keys()))
        assert len(key) == 3, f"Expected 3-tuple key, got: {key}"
        text_hash, model_name, prompt_version = key
        assert prompt_version == "v2"

    def test_v1_db_entry_does_not_satisfy_v2_lookup(self, tmp_db):
        """A v1 cache entry (prompt_version='v1') should be a miss for v2 lookup."""
        from jd_matcher.llm.extract import _jd_hash

        jd_text = "A senior DS role at Acme Corp."
        text_hash = _jd_hash(jd_text)
        model_name = "gpt-4o-mini"

        # Manually insert a v1 row into extraction_cache
        conn = sqlite3.connect(tmp_db)
        try:
            conn.execute(
                "INSERT INTO extraction_cache "
                "(text_hash, model_name, prompt_version, canonical_extraction_json) "
                "VALUES (?, ?, 'v1', ?)",
                (text_hash, model_name, _VALID_V2_JSON),
            )
            conn.commit()
        finally:
            conn.close()

        # v2 lookup should miss
        result = _db_cache_get(tmp_db, text_hash, model_name, "v2")
        assert result is None, "v1 cache entry should not satisfy v2 lookup"

    def test_v2_db_entry_is_found_by_v2_lookup(self, tmp_db):
        """A v2 cache entry is found by a v2 lookup."""
        from jd_matcher.llm.extract import _jd_hash

        jd_text = "An ML Engineer role at Stripe."
        text_hash = _jd_hash(jd_text)
        model_name = "gpt-4o-mini"

        extraction = CanonicalExtraction.model_validate_json(_VALID_V2_JSON)
        _db_cache_put(tmp_db, text_hash, model_name, "v2", extraction)

        result = _db_cache_get(tmp_db, text_hash, model_name, "v2")
        assert result is not None
        assert result.fit_score == extraction.fit_score
        assert result.industry == extraction.industry

    def test_extract_canonical_calls_provider_on_v1_cache_miss(self, tmp_db):
        """With v1 entry in DB, extract_canonical calls the provider (v2 cache miss)."""
        from jd_matcher.llm.extract import _jd_hash
        from unittest.mock import MagicMock

        jd_text = "A pure ML role at DeepMind."
        text_hash = _jd_hash(jd_text)

        # Plant a v1 entry
        conn = sqlite3.connect(tmp_db)
        try:
            conn.execute(
                "INSERT INTO extraction_cache "
                "(text_hash, model_name, prompt_version, canonical_extraction_json) "
                "VALUES (?, 'gpt-4o-mini', 'v1', ?)",
                (text_hash, _VALID_V2_JSON),
            )
            conn.commit()
        finally:
            conn.close()

        provider = _make_v2_provider()
        posting = _make_posting(posting_id=99, full_jd=jd_text)
        extract_canonical(posting, provider=provider, db_path=tmp_db)

        # Provider must have been called (v1 entry ≠ v2 hit)
        provider.extract.assert_called_once()

    def test_extract_canonical_uses_v2_process_cache_on_second_call(self, tmp_db):
        """Second call with same JD uses process cache — provider not called twice."""
        provider = _make_v2_provider()
        posting = _make_posting()
        extract_canonical(posting, provider=provider, db_path=tmp_db)
        extract_canonical(posting, provider=provider, db_path=tmp_db)
        assert provider.extract.call_count == 1


# ---------------------------------------------------------------------------
# AC #5 — Industry taxonomy matches TDD §C18 16-sector list verbatim
# ---------------------------------------------------------------------------


_EXPECTED_INDUSTRIES = [
    "Financial Services / Asset Management",
    "Insurance / Insurtech",
    "Telecom / Digital Services",
    "Gaming / Entertainment",
    "Legal Tech / Compliance",
    "Professional Services / Consulting",
    "Construction / AEC",
    "Energy / Oil & Gas / Cleantech",
    "AI Training / Annotation Platforms",
    "Staffing / Recruiting",
    "AdTech / Marketing Tech",
    "B2B SaaS",
    "Healthcare / Healthtech",
    "Retail / Ecommerce",
    "Government / Public Sector / Crown Corp",
    "Other",
]


class TestIndustryTaxonomy:
    def test_industry_list_has_exactly_16_sectors(self):
        assert len(_INDUSTRY_VALUES) == 16

    def test_industry_list_matches_tdd_verbatim(self):
        assert sorted(_INDUSTRY_VALUES) == sorted(_EXPECTED_INDUSTRIES), (
            f"Industry mismatch.\n"
            f"Extra:   {set(_INDUSTRY_VALUES) - set(_EXPECTED_INDUSTRIES)}\n"
            f"Missing: {set(_EXPECTED_INDUSTRIES) - set(_INDUSTRY_VALUES)}"
        )

    def test_industry_list_matches_test_db_m3_list(self):
        """Cross-check against _VALID_INDUSTRIES in test_init_db_m3 (the DB CHECK constraint source)."""
        db_m3_industries = [
            "Financial Services / Asset Management",
            "Insurance / Insurtech",
            "Telecom / Digital Services",
            "Gaming / Entertainment",
            "Legal Tech / Compliance",
            "Professional Services / Consulting",
            "Construction / AEC",
            "Energy / Oil & Gas / Cleantech",
            "AI Training / Annotation Platforms",
            "Staffing / Recruiting",
            "AdTech / Marketing Tech",
            "B2B SaaS",
            "Healthcare / Healthtech",
            "Retail / Ecommerce",
            "Government / Public Sector / Crown Corp",
            "Other",
        ]
        assert sorted(_INDUSTRY_VALUES) == sorted(db_m3_industries)


# ---------------------------------------------------------------------------
# DB schema — prompt_version column on extraction_cache
# ---------------------------------------------------------------------------


class TestExtractionCacheSchema:
    def test_prompt_version_column_exists_after_init_db(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(extraction_cache);").fetchall()}
        finally:
            conn.close()
        assert "prompt_version" in cols, "prompt_version column missing from extraction_cache"

    def test_existing_rows_default_to_v1(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        try:
            # Insert without specifying prompt_version — should default to 'v1'
            conn.execute(
                "INSERT INTO extraction_cache "
                "(text_hash, model_name, canonical_extraction_json) "
                "VALUES ('abc123', 'gpt-4o-mini', '{}')"
            )
            conn.commit()
            row = conn.execute(
                "SELECT prompt_version FROM extraction_cache WHERE text_hash = 'abc123'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == "v1"
