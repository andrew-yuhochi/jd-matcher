"""Tests for TASK-M2-006 — C18 LLM Extraction.

Coverage:
  - CanonicalExtraction Pydantic model enum enforcement (AC #2)
  - canonical_company normalization — no Inc/Ltd suffixes (AC #3, 5 cases)
  - team_or_department word-count validation (AC #4)
  - 10 synthetic JDs all extract within enum constraints (AC #8)
  - Cache-hit verification — second call does NOT re-invoke provider (AC #5)
  - llm_call_ledger row written per call (AC #6)
  - Retry on transient errors — 3 attempts with backoff (AC #7)
  - Parse-failure → stricter-prompt retry
  - Live test (AC #9) — guarded by SKIP_LIVE env variable
"""

from __future__ import annotations

import json
import os
import sqlite3
import unittest.mock as mock
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.llm.extract import (
    CanonicalExtraction,
    ExtractionParseError,
    PostingRow,
    _PROCESS_CACHE,
    _jd_hash,
    _SENIORITY_VALUES,
    _LOCATION_VALUES,
    extract_canonical,
)
from jd_matcher.llm.providers.base import (
    ExtractionMetadata,
    LLMProviderError,
    ProviderUnavailableError,
    RateLimitError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_META = ExtractionMetadata(
    input_tokens=500, output_tokens=200, latency_ms=800, cost_usd=0.000195
)

_VALID_JSON = json.dumps(
    {
        "canonical_title": "Senior Data Scientist",
        "canonical_company": "Shopify",
        "canonical_seniority": "Senior",
        "canonical_location": "Remote — Canada",
        "team_or_department": "Data Platform",
        "top_skills": ["Python", "SQL", "Spark"],
        "role_summary": (
            "A senior data science role focused on building production ML models. "
            "The team works on data platform infrastructure and analytics tooling. "
            "Core skills include Python, SQL, and distributed computing."
        ),
    }
)


def _make_provider(return_json: str = _VALID_JSON) -> MagicMock:
    p = MagicMock()
    p.extract.return_value = (return_json, _MOCK_META)
    return p


def _make_posting(
    posting_id: int = 1,
    full_jd: str = "A job at Shopify for a Senior Data Scientist in Canada.",
) -> PostingRow:
    return PostingRow(id=posting_id, full_jd=full_jd)


@pytest.fixture(autouse=True)
def clear_process_cache():
    """Ensure the module-level cache is clean between tests."""
    _PROCESS_CACHE.clear()
    yield
    _PROCESS_CACHE.clear()


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_extract.db"
    init_db(db)
    return db


# ---------------------------------------------------------------------------
# AC #2 — Pydantic enum enforcement
# ---------------------------------------------------------------------------


class TestCanonicalExtractionModel:
    def test_valid_seniority_accepted(self):
        for seniority in _SENIORITY_VALUES:
            m = CanonicalExtraction(
                canonical_title="Data Scientist",
                canonical_company="Acme",
                canonical_seniority=seniority,
                canonical_location="Vancouver",
                role_summary="A role.",
            )
            assert m.canonical_seniority == seniority

    def test_invalid_seniority_raises(self):
        with pytest.raises(Exception):
            CanonicalExtraction(
                canonical_title="DS",
                canonical_company="Acme",
                canonical_seniority="Architect",  # not in enum
                canonical_location="Vancouver",
                role_summary="A role.",
            )

    def test_valid_location_accepted(self):
        for loc in _LOCATION_VALUES:
            m = CanonicalExtraction(
                canonical_title="DS",
                canonical_company="Acme",
                canonical_seniority="Mid",
                canonical_location=loc,
                role_summary="A role.",
            )
            assert m.canonical_location == loc

    def test_invalid_location_raises(self):
        with pytest.raises(Exception):
            CanonicalExtraction(
                canonical_title="DS",
                canonical_company="Acme",
                canonical_seniority="Mid",
                canonical_location="New York",  # not in enum
                role_summary="A role.",
            )

    def test_other_location_accepted(self):
        """'Other' is a valid canonical location (the escape valve for rare cities)."""
        m = CanonicalExtraction(
            canonical_title="DS",
            canonical_company="Acme",
            canonical_seniority="Mid",
            canonical_location="Other",
            role_summary="A role.",
        )
        assert m.canonical_location == "Other"

    def test_top_skills_truncated_to_10(self):
        skills = [f"Skill{i}" for i in range(15)]
        m = CanonicalExtraction(
            canonical_title="DS",
            canonical_company="Acme",
            canonical_seniority="Mid",
            canonical_location="Vancouver",
            top_skills=skills,
            role_summary="A role.",
        )
        assert len(m.top_skills) == 10


# ---------------------------------------------------------------------------
# AC #3 — canonical_company normalization (5 cases)
# ---------------------------------------------------------------------------


class TestCompanyNormalization:
    def _make(self, company: str) -> CanonicalExtraction:
        return CanonicalExtraction(
            canonical_title="DS",
            canonical_company=company,
            canonical_seniority="Mid",
            canonical_location="Toronto",
            role_summary="A role.",
        )

    def test_strips_inc(self):
        assert self._make("Shopify Inc.").canonical_company == "Shopify"

    def test_strips_ltd(self):
        assert self._make("SomeBank Ltd").canonical_company == "SomeBank"

    def test_strips_canada_inc(self):
        assert self._make("Lululemon Athletica Canada Inc.").canonical_company == (
            "Lululemon Athletica"
        )

    def test_strips_corp(self):
        assert self._make("Data Corp.").canonical_company == "Data"

    def test_strips_limited(self):
        assert self._make("Acme Limited").canonical_company == "Acme"

    def test_no_suffix_unchanged(self):
        assert self._make("TD Bank").canonical_company == "TD Bank"


# ---------------------------------------------------------------------------
# AC #4 — team_or_department canonical format
# ---------------------------------------------------------------------------


class TestTeamOrDepartment:
    def test_none_accepted(self):
        m = CanonicalExtraction(
            canonical_title="DS",
            canonical_company="Acme",
            canonical_seniority="Mid",
            canonical_location="Vancouver",
            team_or_department=None,
            role_summary="A role.",
        )
        assert m.team_or_department is None

    def test_two_word_team_accepted(self):
        m = CanonicalExtraction(
            canonical_title="DS",
            canonical_company="Acme",
            canonical_seniority="Mid",
            canonical_location="Vancouver",
            team_or_department="Risk Analytics",
            role_summary="A role.",
        )
        assert m.team_or_department == "Risk Analytics"

    def test_five_word_team_accepted(self):
        m = CanonicalExtraction(
            canonical_title="DS",
            canonical_company="Acme",
            canonical_seniority="Mid",
            canonical_location="Vancouver",
            team_or_department="Applied Machine Learning Research",
            role_summary="A role.",
        )
        assert m.team_or_department == "Applied Machine Learning Research"


# ---------------------------------------------------------------------------
# AC #8 — 10 synthetic JDs extract within enum constraints
# ---------------------------------------------------------------------------

_SYNTHETIC_JDS = [
    (
        "junior-software-engineer",
        "We are looking for a Junior Software Engineer to join our Backend Engineering team "
        "in Vancouver, BC. You will work with Python, PostgreSQL, and Docker.",
        {
            "canonical_title": "Junior Software Engineer",
            "canonical_company": "TechCo",
            "canonical_seniority": "Junior",
            "canonical_location": "Vancouver",
            "team_or_department": "Backend Engineering",
            "top_skills": ["Python", "PostgreSQL", "Docker"],
            "role_summary": "A junior engineering role building backend services.",
        },
    ),
    (
        "senior-data-scientist-remote",
        "Senior Data Scientist at Shopify Inc. — 100% Remote (Canada). "
        "You will lead ML model development using Python, Spark, and dbt.",
        {
            "canonical_title": "Senior Data Scientist",
            "canonical_company": "Shopify",
            "canonical_seniority": "Senior",
            "canonical_location": "Remote — Canada",
            "team_or_department": "Data Platform",
            "top_skills": ["Python", "Spark", "dbt"],
            "role_summary": "A senior data science role at a Canadian e-commerce company.",
        },
    ),
    (
        "staff-ml-engineer-toronto",
        "Staff ML Engineer - Toronto, Ontario. Work on recommendation systems "
        "and production ML infrastructure. Exp with PyTorch, Kubernetes, Kafka required.",
        {
            "canonical_title": "Staff ML Engineer",
            "canonical_company": "Acme AI",
            "canonical_seniority": "Staff",
            "canonical_location": "Toronto",
            "team_or_department": "Applied Machine Learning",
            "top_skills": ["PyTorch", "Kubernetes", "Kafka"],
            "role_summary": "A staff ML engineering role building recommendation systems.",
        },
    ),
    (
        "principal-data-engineer-calgary",
        "Principal Data Engineer, Calgary AB. Architect large-scale data pipelines. "
        "Expert in Spark, Airflow, dbt, Snowflake, Terraform.",
        {
            "canonical_title": "Principal Data Engineer",
            "canonical_company": "Energy Corp",
            "canonical_seniority": "Principal",
            "canonical_location": "Calgary",
            "team_or_department": "Data Platform",
            "top_skills": ["Spark", "Airflow", "dbt", "Snowflake", "Terraform"],
            "role_summary": "A principal engineering role designing data infrastructure.",
        },
    ),
    (
        "lead-analytics-engineer-montreal",
        "Lead Analytics Engineer - Montreal. Drive data models and BI tooling. "
        "Requires dbt, SQL, Looker, Tableau. Hybrid schedule.",
        {
            "canonical_title": "Lead Analytics Engineer",
            "canonical_company": "FinanceCo",
            "canonical_seniority": "Lead",
            "canonical_location": "Hybrid — Montreal",
            "team_or_department": "Analytics Engineering",
            "top_skills": ["dbt", "SQL", "Looker", "Tableau"],
            "role_summary": "A lead analytics engineering role building BI tooling.",
        },
    ),
    (
        "manager-data-science-ottawa",
        "Manager, Data Science - Ottawa, ON. Lead a team of 6 data scientists. "
        "Python, A/B testing, experimentation platform.",
        {
            "canonical_title": "Manager Data Science",
            "canonical_company": "GovTech",
            "canonical_seniority": "Manager",
            "canonical_location": "Ottawa",
            "team_or_department": "Data Science",
            "top_skills": ["Python", "A/B testing"],
            "role_summary": "A data science management role leading a team of six.",
        },
    ),
    (
        "director-analytics-remote-na",
        "Director of Analytics - Remote (US and Canada). Own analytics strategy across "
        "product and growth. SQL, Looker, Python, experimentation.",
        {
            "canonical_title": "Director of Analytics",
            "canonical_company": "ScaleCo",
            "canonical_seniority": "Director",
            "canonical_location": "Remote — North America",
            "team_or_department": None,
            "top_skills": ["SQL", "Looker", "Python"],
            "role_summary": "A director-level analytics role with cross-functional scope.",
        },
    ),
    (
        "mid-data-analyst-edmonton",
        "Data Analyst II, Edmonton, Alberta. Analyze customer data and build dashboards. "
        "SQL, Excel, Tableau, Power BI.",
        {
            "canonical_title": "Data Analyst",
            "canonical_company": "UtilityCo",
            "canonical_seniority": "Mid",
            "canonical_location": "Edmonton",
            "team_or_department": "Business Analytics",
            "top_skills": ["SQL", "Excel", "Tableau", "Power BI"],
            "role_summary": "A mid-level data analyst role building customer dashboards.",
        },
    ),
    (
        "senior-mle-burnaby",
        "Senior Machine Learning Engineer — Burnaby, BC (hybrid). "
        "Build production ML pipelines. PyTorch, MLflow, Kubernetes, Python, AWS.",
        {
            "canonical_title": "Senior Machine Learning Engineer",
            "canonical_company": "StartupCo",
            "canonical_seniority": "Senior",
            "canonical_location": "Hybrid — Vancouver",  # Burnaby → Vancouver
            "team_or_department": "Machine Learning",
            "top_skills": ["PyTorch", "MLflow", "Kubernetes", "Python", "AWS"],
            "role_summary": "A senior MLE role building production ML pipelines near Vancouver.",
        },
    ),
    (
        "mid-ds-no-team",
        "Data Scientist. No specific team mentioned. Python, R, SQL. Halifax, NS.",
        {
            "canonical_title": "Data Scientist",
            "canonical_company": "Consulting Inc.",
            "canonical_seniority": "Mid",
            "canonical_location": "Halifax",
            "team_or_department": None,
            "top_skills": ["Python", "R", "SQL"],
            "role_summary": "A data science role at a consulting firm in Halifax.",
        },
    ),
]


class TestSyntheticJDs:
    """AC #8: 10 hand-crafted synthetic JDs must extract within enum constraints."""

    @pytest.mark.parametrize("jd_id,jd_text,expected_json", _SYNTHETIC_JDS)
    def test_enum_constraints_satisfied(
        self, jd_id: str, jd_text: str, expected_json: dict, tmp_db: Path
    ):
        """Mock provider returns the expected JSON; validate enum constraints hold."""
        raw = json.dumps(expected_json)
        provider = _make_provider(raw)
        posting = _make_posting(posting_id=hash(jd_id) & 0xFFFF, full_jd=jd_text)

        result = extract_canonical(posting, provider=provider, db_path=tmp_db)

        assert result.canonical_seniority in _SENIORITY_VALUES, (
            f"[{jd_id}] seniority '{result.canonical_seniority}' is not in enum"
        )
        assert result.canonical_location in _LOCATION_VALUES, (
            f"[{jd_id}] location '{result.canonical_location}' is not in enum"
        )
        assert result.canonical_title
        assert result.canonical_company
        assert result.role_summary


# ---------------------------------------------------------------------------
# AC #5 — Cache hit: second call does not invoke provider again
# ---------------------------------------------------------------------------


class TestCacheHit:
    def test_in_process_cache_prevents_second_provider_call(self, tmp_db: Path):
        provider = _make_provider()
        posting = _make_posting(full_jd="Unique JD text for cache test.")

        result1 = extract_canonical(posting, provider=provider, db_path=tmp_db)
        result2 = extract_canonical(posting, provider=provider, db_path=tmp_db)

        assert provider.extract.call_count == 1, (
            f"Expected 1 provider call, got {provider.extract.call_count}"
        )
        assert result1 == result2

    def test_db_cache_prevents_provider_call_across_processes(self, tmp_db: Path):
        """Simulate cross-process reuse: fill DB cache, clear in-process, call again."""
        provider = _make_provider()
        posting = _make_posting(full_jd="DB cache test JD content.")

        extract_canonical(posting, provider=provider, db_path=tmp_db)
        assert provider.extract.call_count == 1

        # Simulate a new process by clearing the in-process cache
        _PROCESS_CACHE.clear()

        provider2 = _make_provider()
        extract_canonical(posting, provider=provider2, db_path=tmp_db)
        # DB cache should have been hit — provider2 should not be called
        assert provider2.extract.call_count == 0

    def test_different_jd_texts_get_separate_cache_entries(self, tmp_db: Path):
        provider = _make_provider()
        posting_a = _make_posting(posting_id=10, full_jd="JD text A for caching.")
        posting_b = _make_posting(posting_id=11, full_jd="JD text B entirely different.")

        extract_canonical(posting_a, provider=provider, db_path=tmp_db)
        extract_canonical(posting_b, provider=provider, db_path=tmp_db)

        assert provider.extract.call_count == 2


# ---------------------------------------------------------------------------
# AC #6 — llm_call_ledger row written per call
# ---------------------------------------------------------------------------


class TestLedgerWrites:
    def test_ledger_row_written_on_success(self, tmp_db: Path):
        provider = _make_provider()
        posting = _make_posting(full_jd="JD for ledger row test.")
        extract_canonical(posting, provider=provider, db_path=tmp_db)

        conn = sqlite3.connect(tmp_db)
        try:
            rows = conn.execute(
                "SELECT status, call_kind, provider, model_name, cost_usd "
                "FROM llm_call_ledger WHERE status = 'success'"
            ).fetchall()
        finally:
            conn.close()

        assert len(rows) >= 1
        status, call_kind, prov, model, cost = rows[0]
        assert status == "success"
        assert call_kind == "extraction"
        assert prov == "openai"
        assert cost > 0

    def test_ledger_row_written_on_cache_hit(self, tmp_db: Path):
        provider = _make_provider()
        posting = _make_posting(full_jd="JD for cache-hit ledger test.")

        extract_canonical(posting, provider=provider, db_path=tmp_db)
        extract_canonical(posting, provider=provider, db_path=tmp_db)  # cache hit

        conn = sqlite3.connect(tmp_db)
        try:
            rows = conn.execute(
                "SELECT status FROM llm_call_ledger ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

        statuses = [r[0] for r in rows]
        assert "success" in statuses
        assert "cache_hit" in statuses

    def test_no_ledger_write_when_db_path_is_none(self):
        """db_path=None disables all ledger writes — useful in unit tests."""
        provider = _make_provider()
        posting = _make_posting()
        # Should not raise; no DB writes attempted
        result = extract_canonical(posting, provider=provider, db_path=None)
        assert result.canonical_title


# ---------------------------------------------------------------------------
# AC #7 — Retry on transient errors (3 attempts with exponential backoff)
# ---------------------------------------------------------------------------


class TestTransientErrorRetry:
    def test_rate_limit_error_retried_three_times(self, tmp_db: Path):
        """Provider raises RateLimitError twice, succeeds on third attempt."""
        provider = MagicMock()
        provider.extract.side_effect = [
            RateLimitError("429"),
            RateLimitError("429"),
            (_VALID_JSON, _MOCK_META),
        ]
        posting = _make_posting(full_jd="Rate limit retry test JD.")

        with patch("jd_matcher.llm.extract.time.sleep"):  # speed up backoff
            result = extract_canonical(posting, provider=provider, db_path=tmp_db)

        assert result.canonical_title == "Senior Data Scientist"
        assert provider.extract.call_count == 3

        conn = sqlite3.connect(tmp_db)
        try:
            rows = conn.execute(
                "SELECT status FROM llm_call_ledger ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        statuses = [r[0] for r in rows]
        assert statuses.count("retry") == 2
        assert statuses.count("success") == 1

    def test_provider_unavailable_error_retried(self, tmp_db: Path):
        provider = MagicMock()
        provider.extract.side_effect = [
            ProviderUnavailableError("network error"),
            (_VALID_JSON, _MOCK_META),
        ]
        posting = _make_posting(full_jd="Network error retry test JD.")

        with patch("jd_matcher.llm.extract.time.sleep"):
            result = extract_canonical(posting, provider=provider, db_path=tmp_db)

        assert result.canonical_title
        assert provider.extract.call_count == 2

    def test_all_three_attempts_fail_raises(self, tmp_db: Path):
        provider = MagicMock()
        provider.extract.side_effect = RateLimitError("429")
        posting = _make_posting(full_jd="All three attempts fail JD.")

        with patch("jd_matcher.llm.extract.time.sleep"):
            with pytest.raises(LLMProviderError):
                extract_canonical(posting, provider=provider, db_path=tmp_db)

        assert provider.extract.call_count == 3


# ---------------------------------------------------------------------------
# Parse-failure → stricter-prompt retry
# ---------------------------------------------------------------------------


class TestParseFailureRetry:
    def test_bad_seniority_retried_with_stricter_prompt(self, tmp_db: Path):
        """Provider returns invalid seniority twice, then corrects on third attempt."""
        bad_json = json.dumps(
            {
                "canonical_title": "DS",
                "canonical_company": "Acme",
                "canonical_seniority": "Architect",  # invalid
                "canonical_location": "Vancouver",
                "team_or_department": None,
                "top_skills": ["Python"],
                "role_summary": "A role.",
            }
        )
        provider = MagicMock()
        provider.extract.side_effect = [
            (bad_json, _MOCK_META),
            (bad_json, _MOCK_META),
            (_VALID_JSON, _MOCK_META),
        ]
        posting = _make_posting(full_jd="Bad seniority JD test.")

        result = extract_canonical(posting, provider=provider, db_path=tmp_db)

        assert result.canonical_seniority == "Senior"
        assert provider.extract.call_count == 3

        # Verify the stricter prompt was used on retries
        second_call_prompt = provider.extract.call_args_list[1][1]["prompt"]
        assert "INVALID" in second_call_prompt or "INVALID" in str(
            provider.extract.call_args_list[1]
        )

    def test_all_parse_attempts_fail_raises_extraction_parse_error(self, tmp_db: Path):
        bad_json = json.dumps(
            {
                "canonical_title": "DS",
                "canonical_company": "Acme",
                "canonical_seniority": "Overlord",  # never valid
                "canonical_location": "Mars",  # never valid
                "role_summary": "A role.",
            }
        )
        provider = MagicMock()
        provider.extract.return_value = (bad_json, _MOCK_META)
        posting = _make_posting(full_jd="All parse failures JD test.")

        with pytest.raises(ExtractionParseError):
            extract_canonical(posting, provider=provider, db_path=tmp_db)

    def test_bad_json_parse_failure_retried(self, tmp_db: Path):
        """Non-JSON response (not a valid dict) causes parse failure and retry."""
        provider = MagicMock()
        provider.extract.side_effect = [
            ('{"malformed": true', _MOCK_META),  # incomplete JSON
            (_VALID_JSON, _MOCK_META),
        ]
        posting = _make_posting(full_jd="Malformed JSON retry test JD.")

        result = extract_canonical(posting, provider=provider, db_path=tmp_db)
        assert result.canonical_title


# ---------------------------------------------------------------------------
# extraction_cache table existence (schema migration)
# ---------------------------------------------------------------------------


class TestExtractionCacheTable:
    def test_extraction_cache_table_exists(self, tmp_db: Path):
        conn = sqlite3.connect(tmp_db)
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "extraction_cache" in tables

    def test_extraction_cache_primary_key_is_text_hash_and_model(self, tmp_db: Path):
        """Two rows with same text_hash + model_name → IntegrityError."""
        conn = sqlite3.connect(tmp_db)
        try:
            conn.execute(
                "INSERT INTO extraction_cache (text_hash, model_name, canonical_extraction_json) "
                "VALUES ('hash123', 'gpt-4o-mini', '{}')"
            )
            conn.commit()
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO extraction_cache (text_hash, model_name, canonical_extraction_json) "
                    "VALUES ('hash123', 'gpt-4o-mini', '{}')"
                )
                conn.commit()
        finally:
            conn.rollback()
            conn.close()


# ---------------------------------------------------------------------------
# TestCacheHitPropagation — asserts that postings fields are populated on cache hit
# (closes the coverage gap that allowed the M2-012 Jobright bug class to ship)
# ---------------------------------------------------------------------------


class TestCacheHitPropagation:
    """Verify that _write_postings_extracted() fires on BOTH fresh and cache-hit paths.

    M2-012 root cause: extract_canonical() wrote to extraction_cache but never
    to postings, so cache-hit paths left postings.top_skills / canonical_seniority /
    role_summary NULL. TASK-M3-000 adds _write_postings_extracted() to all three
    return paths (fresh, in-process cache, DB cache).
    """

    def test_fresh_extraction_populates_postings(self, tmp_db: Path) -> None:
        """After a fresh extraction, postings.canonical_seniority and top_skills are non-null."""
        provider = _make_provider()
        posting = _make_posting(posting_id=100, full_jd="Fresh extraction JD text.")

        # Insert the posting into the DB so _write_postings_extracted has a row to update
        conn = sqlite3.connect(tmp_db)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            INSERT INTO postings
                (id, user_id, canonical_title, hydration_status, full_jd, first_seen, last_seen)
            VALUES (100, 'default', 'Test Role', 'complete', 'Fresh extraction JD text.',
                    '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
            """
        )
        conn.commit()
        conn.close()

        extract_canonical(posting, provider=provider, db_path=tmp_db)

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT canonical_seniority, top_skills, role_summary FROM postings WHERE id = 100"
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "Senior", f"canonical_seniority should be 'Senior', got {row[0]!r}"
        assert row[1] is not None, "top_skills should be non-null after extraction"
        assert row[2] is not None, "role_summary should be non-null after extraction"

    def test_db_cache_hit_propagates_to_postings(self, tmp_db: Path) -> None:
        """On a DB cache hit, postings fields are updated from the cached extraction.

        This is the exact class of bug from M2-012 (Jobright canonicals 316/395/396/458):
        the cache was hit correctly but postings remained NULL.
        """
        provider = _make_provider()
        # First call: fresh extraction; populates extraction_cache
        posting_seed = _make_posting(posting_id=200, full_jd="Cache hit propagation JD text.")
        conn = sqlite3.connect(tmp_db)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            INSERT INTO postings
                (id, user_id, canonical_title, hydration_status, full_jd, first_seen, last_seen)
            VALUES (200, 'default', 'Seed Role', 'complete', 'Cache hit propagation JD text.',
                    '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
            """
        )
        conn.commit()
        conn.close()
        extract_canonical(posting_seed, provider=provider, db_path=tmp_db)

        # Second posting with the SAME full_jd → DB cache hit path
        conn = sqlite3.connect(tmp_db)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            INSERT INTO postings
                (id, user_id, canonical_title, hydration_status, full_jd, first_seen, last_seen)
            VALUES (201, 'default', 'Cache Hit Role', 'complete', 'Cache hit propagation JD text.',
                    '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
            """
        )
        conn.commit()
        conn.close()

        # Clear the in-process cache so the DB cache path is exercised
        _PROCESS_CACHE.clear()

        posting_hit = _make_posting(posting_id=201, full_jd="Cache hit propagation JD text.")
        extract_canonical(posting_hit, provider=provider, db_path=tmp_db)

        # Provider should have been called only ONCE (for the seed posting)
        assert provider.extract.call_count == 1, (
            "Provider should not be called on cache hit"
        )

        # The cache-hit posting must now have its fields populated
        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT canonical_seniority, top_skills, role_summary FROM postings WHERE id = 201"
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "Senior", (
            f"postings.canonical_seniority should be 'Senior' on cache hit, got {row[0]!r}"
        )
        assert row[1] is not None, "postings.top_skills should be non-null on cache hit"
        assert row[2] is not None, "postings.role_summary should be non-null on cache hit"


# ---------------------------------------------------------------------------
# AC #9 — Live test (one real posting, real OpenAI call)
# ---------------------------------------------------------------------------

SKIP_LIVE = os.environ.get("SKIP_LIVE", "1") == "1"


@pytest.mark.skipif(SKIP_LIVE, reason="SKIP_LIVE=1 — set SKIP_LIVE=0 to run live tests")
class TestLiveExtraction:
    def test_real_posting_extracts_valid_canonical_fields(self):
        """AC #9: Live extraction against a real posting in the user's DB."""
        import sqlite3 as _sqlite

        real_db = Path.home() / ".jd-matcher" / "jd-matcher.db"
        assert real_db.exists(), f"Real DB not found at {real_db}"

        conn = _sqlite.connect(real_db)
        try:
            row = conn.execute(
                "SELECT id, full_jd, canonical_company, canonical_title, canonical_location "
                "FROM postings WHERE full_jd IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()

        assert row is not None, "No postings with full_jd found"
        pid, full_jd, company, title, location = row
        posting = PostingRow(
            id=pid, full_jd=full_jd, canonical_company=company,
            canonical_title=title, canonical_location=location
        )
        priors: dict[str, str] = {}
        if company:
            priors["company"] = company
        if title:
            priors["title"] = title

        result = extract_canonical(posting, db_path=real_db, priors=priors or None)

        # Verify all canonical fields populated
        assert result.canonical_title, "canonical_title is empty"
        assert result.canonical_company, "canonical_company is empty"
        assert result.canonical_seniority in _SENIORITY_VALUES, (
            f"canonical_seniority '{result.canonical_seniority}' not in enum"
        )
        assert result.canonical_location in _LOCATION_VALUES, (
            f"canonical_location '{result.canonical_location}' not in enum"
        )
        assert result.role_summary, "role_summary is empty"
        assert len(result.top_skills) > 0, "top_skills is empty"

        # Verify no Inc/Ltd in company name (visual check via assertion)
        import re
        suffix_pattern = r"\s*(Inc\.?|Ltd\.?|Corp\.?|Limited)\s*$"
        assert not re.search(suffix_pattern, result.canonical_company, re.IGNORECASE), (
            f"canonical_company still has legal suffix: {result.canonical_company}"
        )
