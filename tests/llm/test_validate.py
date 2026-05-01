"""Tests for TASK-M2-006 Calibration Phase A — extraction validator CLI.

Coverage:
  - C19 filter correctly partitions 5 postings into 3 pass / 2 filtered
  - run_validation extracts only the 3 passing postings (not the 2 filtered)
  - generate_report contains all 3 extracted IDs and none of the 2 filtered
  - Mocked OpenAI client — zero token spend
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.llm.extract import _PROCESS_CACHE
from jd_matcher.llm.providers.base import ExtractionMetadata
from jd_matcher.llm.validate import (
    PostingRecord,
    RunStats,
    _apply_c19_filter,
    _bust_cache_for_ids,
    _fetch_all_postings,
    generate_report,
    run_validation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_META = ExtractionMetadata(
    input_tokens=400, output_tokens=150, latency_ms=600, cost_usd=0.000150
)


def _valid_json(title: str = "Senior Data Scientist", company: str = "Shopify") -> str:
    return json.dumps(
        {
            "canonical_title": title,
            "canonical_company": company,
            "canonical_seniority": "Senior",
            "canonical_location": "Vancouver",
            "team_or_department": "Data Platform",
            "top_skills": ["Python", "SQL", "Spark"],
            "role_summary": (
                "A senior data science role working on production ML systems. "
                "The team focuses on data platform reliability and scale."
            ),
            # M3 v2 required fields
            "fit_score": 5,
            "fit_reasoning": "Core DS role with production ML focus.",
            "industry": "B2B SaaS",
            "role_orientation": ["Problem-Solving", "Engineering"],
            "salary_min_cad": None,
            "salary_max_cad": None,
            "citizenship_requirement": "not_mentioned",
            "citizenship_reason": "",
            "can_hire_in_canada": "yes",
        }
    )


def _make_mock_provider(json_str: str | None = None) -> MagicMock:
    p = MagicMock()
    p.extract.return_value = (json_str or _valid_json(), _MOCK_META)
    return p


@pytest.fixture(autouse=True)
def clear_process_cache():
    _PROCESS_CACHE.clear()
    yield
    _PROCESS_CACHE.clear()


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_validate.db"
    init_db(db)
    return db


def _insert_posting(
    conn: sqlite3.Connection,
    *,
    posting_id: int,
    canonical_title: str,
    canonical_company: str = "Acme",
    full_jd: str = "A job description.",
    source: str = "linkedin_email",
) -> None:
    conn.execute(
        "INSERT INTO postings (id, canonical_title, canonical_company, full_jd, first_seen, last_seen) "
        "VALUES (?, ?, ?, ?, '2026-01-01', '2026-01-01')",
        (posting_id, canonical_title, canonical_company, full_jd),
    )
    conn.execute(
        "INSERT INTO posting_sources (posting_id, source, source_url, source_first_seen) "
        "VALUES (?, ?, 'https://example.com', '2026-01-01')",
        (posting_id, source),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Five-posting fixture:
#   IDs 1,2,3 should PASS C19 (DS/ML roles)
#   IDs 4,5 should DROP (entry-level + non-technical)
# ---------------------------------------------------------------------------

# These titles are deliberately chosen to match the actual config so the tests
# are realistic rather than config-duplicating. "Junior" hits the pre_deny list;
# "Office Manager" hits the deny list (non-technical).
_PASS_TITLES = [
    "Senior Data Scientist",
    "Machine Learning Engineer",
    "Data Engineer",
]
_FAIL_TITLES = [
    "Junior Software Engineer",  # pre_deny: junior
    "Sales Representative",  # deny: sales
]


@pytest.fixture()
def five_posting_db(tmp_db: Path) -> Path:
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    try:
        for i, title in enumerate(_PASS_TITLES, start=1):
            _insert_posting(
                conn,
                posting_id=i,
                canonical_title=title,
                canonical_company=f"Company{i}",
                full_jd=f"Full JD for posting {i}: {title} role.",
            )
        for i, title in enumerate(_FAIL_TITLES, start=4):
            _insert_posting(
                conn,
                posting_id=i,
                canonical_title=title,
                canonical_company=f"Company{i}",
                full_jd=f"Full JD for posting {i}: {title} role.",
            )
    finally:
        conn.close()
    return tmp_db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestC19InMemoryFilter:
    """_apply_c19_filter correctly splits the 5 postings into 3 pass / 2 drop."""

    def test_three_pass_two_drop(self, five_posting_db: Path) -> None:
        all_postings = _fetch_all_postings(five_posting_db)
        assert len(all_postings) == 5

        passing = _apply_c19_filter(all_postings)
        passing_ids = {p.id for p in passing}
        failing_ids = {p.id for p in all_postings if p.id not in passing_ids}

        assert passing_ids == {1, 2, 3}, f"Expected IDs 1,2,3 to pass; got {passing_ids}"
        assert failing_ids == {4, 5}, f"Expected IDs 4,5 to fail; got {failing_ids}"


class TestRunValidation:
    """run_validation only extracts the 3 C19-passing postings."""

    def test_extracts_only_passing_postings(self, five_posting_db: Path) -> None:
        mock_provider = _make_mock_provider()

        # Patch extract_canonical to use our mock provider
        import unittest.mock as mock
        from jd_matcher.llm import validate as validate_mod

        original_extract = validate_mod.extract_canonical

        def patched_extract(posting, *, db_path=None, priors=None, **kwargs):
            return original_extract(
                posting,
                provider=mock_provider,
                db_path=db_path,
                priors=priors,
            )

        with mock.patch.object(validate_mod, "extract_canonical", side_effect=patched_extract):
            results, stats = run_validation(five_posting_db)

        assert stats.analyzed == 3, f"Expected 3 analyzed, got {stats.analyzed}"
        assert stats.success == 3, f"Expected 3 successes, got {stats.success}"
        assert len(stats.failures) == 0

        extracted_ids = {r.posting.id for r in results}
        assert extracted_ids == {1, 2, 3}, f"Unexpected extracted IDs: {extracted_ids}"

        # Provider was called exactly 3 times (no caching in this fresh DB)
        assert mock_provider.extract.call_count == 3

    def test_limit_flag_respected(self, five_posting_db: Path) -> None:
        import unittest.mock as mock
        from jd_matcher.llm import validate as validate_mod

        original_extract = validate_mod.extract_canonical
        mock_provider = _make_mock_provider()

        def patched_extract(posting, *, db_path=None, priors=None, **kwargs):
            return original_extract(
                posting,
                provider=mock_provider,
                db_path=db_path,
                priors=priors,
            )

        with mock.patch.object(validate_mod, "extract_canonical", side_effect=patched_extract):
            results, stats = run_validation(five_posting_db, limit=2)

        assert stats.analyzed == 2
        assert stats.success == 2
        assert mock_provider.extract.call_count == 2


class TestGenerateReport:
    """generate_report includes the 3 extracted postings and not the 2 filtered."""

    def test_report_contains_passing_ids_not_filtered(self, five_posting_db: Path) -> None:
        import unittest.mock as mock
        from jd_matcher.llm import validate as validate_mod

        original_extract = validate_mod.extract_canonical
        mock_provider = _make_mock_provider()

        def patched_extract(posting, *, db_path=None, priors=None, **kwargs):
            return original_extract(
                posting,
                provider=mock_provider,
                db_path=db_path,
                priors=priors,
            )

        with mock.patch.object(validate_mod, "extract_canonical", side_effect=patched_extract):
            results, stats = run_validation(five_posting_db)

        report = generate_report(results, stats, five_posting_db)

        # The report must be a non-empty Markdown string
        assert "# TASK-M2-006" in report
        assert "## Extractions" in report

        # Passing posting IDs appear in the table
        for pid in [1, 2, 3]:
            assert f"| {pid} |" in report, f"Posting ID {pid} missing from report table"

        # Filtered posting IDs must NOT appear in the table rows
        for pid in [4, 5]:
            # They could appear in the summary counts as "0 failures" etc., but
            # not as data rows in the table section. We check the table section only.
            table_start = report.index("## Extractions")
            table_section = report[table_start:]
            assert f"| {pid} |" not in table_section, (
                f"Filtered posting ID {pid} unexpectedly appears in report table"
            )

    def test_report_summary_metrics_correct(self, five_posting_db: Path) -> None:
        import unittest.mock as mock
        from jd_matcher.llm import validate as validate_mod

        original_extract = validate_mod.extract_canonical
        mock_provider = _make_mock_provider()

        def patched_extract(posting, *, db_path=None, priors=None, **kwargs):
            return original_extract(
                posting,
                provider=mock_provider,
                db_path=db_path,
                priors=priors,
            )

        with mock.patch.object(validate_mod, "extract_canonical", side_effect=patched_extract):
            results, stats = run_validation(five_posting_db)

        report = generate_report(results, stats, five_posting_db)

        assert "| Postings analyzed | 3 |" in report
        assert "| Successful extractions | 3 |" in report
        assert "| Parse failures (3-retry exhausted) | 0 |" in report


class TestBustCacheForIds:
    """_bust_cache_for_ids deletes the correct extraction_cache rows."""

    def test_bust_removes_cache_row_for_target_ids(self, five_posting_db: Path) -> None:
        import hashlib
        import sqlite3

        full_jd_1 = "Full JD for posting 1: Senior Data Scientist role."
        text_hash_1 = hashlib.sha256(full_jd_1.encode("utf-8")).hexdigest()

        # Manually insert a fake extraction_cache row for posting 1
        conn = sqlite3.connect(five_posting_db)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO extraction_cache "
                "(text_hash, model_name, canonical_extraction_json, user_id) "
                "VALUES (?, 'gpt-4o-mini', '{\"canonical_title\":\"x\",\"canonical_company\":\"y\","
                "\"canonical_seniority\":\"Mid\",\"canonical_location\":\"Vancouver\","
                "\"team_or_department\":null,\"top_skills\":[],\"role_summary\":\"r\"}', 'default')",
                (text_hash_1,),
            )
            conn.commit()
            # Confirm it's there
            row = conn.execute(
                "SELECT text_hash FROM extraction_cache WHERE text_hash = ?", (text_hash_1,)
            ).fetchone()
            assert row is not None, "Cache row should exist before busting"
        finally:
            conn.close()

        # Also plant it in the process cache (3-tuple key since v2)
        _PROCESS_CACHE[(text_hash_1, "gpt-4o-mini", "v2")] = None  # type: ignore[assignment]

        # Run bust for posting ID 1
        deleted = _bust_cache_for_ids(five_posting_db, [1])

        # DB row should be gone
        conn2 = sqlite3.connect(five_posting_db)
        try:
            remaining = conn2.execute(
                "SELECT text_hash FROM extraction_cache WHERE text_hash = ?", (text_hash_1,)
            ).fetchone()
        finally:
            conn2.close()
        assert remaining is None, "Cache row should be deleted after busting"

        # Process cache entry should be evicted (bust evicts all keys with this hash)
        assert (text_hash_1, "gpt-4o-mini", "v2") not in _PROCESS_CACHE

    def test_bust_does_not_remove_other_ids(self, five_posting_db: Path) -> None:
        import hashlib
        import sqlite3

        full_jd_2 = "Full JD for posting 2: Machine Learning Engineer role."
        text_hash_2 = hashlib.sha256(full_jd_2.encode("utf-8")).hexdigest()
        full_jd_3 = "Full JD for posting 3: Data Engineer role."
        text_hash_3 = hashlib.sha256(full_jd_3.encode("utf-8")).hexdigest()

        conn = sqlite3.connect(five_posting_db)
        fake_json = (
            '{"canonical_title":"x","canonical_company":"y","canonical_seniority":"Mid",'
            '"canonical_location":"Vancouver","team_or_department":null,"top_skills":[],'
            '"role_summary":"r"}'
        )
        try:
            for h in (text_hash_2, text_hash_3):
                conn.execute(
                    "INSERT OR REPLACE INTO extraction_cache "
                    "(text_hash, model_name, canonical_extraction_json, user_id) "
                    "VALUES (?, 'gpt-4o-mini', ?, 'default')",
                    (h, fake_json),
                )
            conn.commit()
        finally:
            conn.close()

        # Only bust posting 2, not posting 3
        _bust_cache_for_ids(five_posting_db, [2])

        conn2 = sqlite3.connect(five_posting_db)
        try:
            row2 = conn2.execute(
                "SELECT text_hash FROM extraction_cache WHERE text_hash = ?", (text_hash_2,)
            ).fetchone()
            row3 = conn2.execute(
                "SELECT text_hash FROM extraction_cache WHERE text_hash = ?", (text_hash_3,)
            ).fetchone()
        finally:
            conn2.close()

        assert row2 is None, "Posting 2 cache should be deleted"
        assert row3 is not None, "Posting 3 cache should be untouched"

    def test_bust_empty_list_is_noop(self, five_posting_db: Path) -> None:
        deleted = _bust_cache_for_ids(five_posting_db, [])
        assert deleted == 0
