"""Tests for TASK-M3-001: M3 schema migration — 11 new columns + 1 sort index."""

from __future__ import annotations

import sqlite3

import pytest

from jd_matcher.db.init_db import init_db

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

NEW_M3_COLUMNS = {
    "fit_score",
    "fit_reasoning",
    "industry",
    "role_orientation",
    "salary_min_cad",
    "salary_max_cad",
    "citizenship_requirement",
    "citizenship_reason",
    "can_hire_in_canada",
    "is_filtered",
    "filter_reason",
}

NEW_M3_INDEX = "idx_canonical_user_main_rank"

_VALID_INDUSTRIES = [
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


@pytest.fixture()
def tmp_db(tmp_path):
    """Return a Path to a freshly initialised test database."""
    db_path = tmp_path / "test_m3.db"
    init_db(db_path)
    return db_path


def _canonical_columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(canonical_postings);").fetchall()}


def _insert_minimal_canonical(conn: sqlite3.Connection, now: str = "2026-05-01T00:00:00Z") -> int:
    """Insert a minimal canonical row (no M3 fields) and return its rowid."""
    cur = conn.execute(
        "INSERT INTO canonical_postings "
        "(canonical_title, canonical_company, canonical_seniority, canonical_location, "
        "top_skills, role_summary, full_jd, full_jd_provenance, "
        "first_seen, last_seen, sources_summary) "
        "VALUES ('Data Scientist', 'Acme', 'mid', 'Vancouver', '[]', 'summary', "
        "'full jd', '{}', ?, ?, '[\"linkedin\"]');",
        (now, now),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Column presence
# ---------------------------------------------------------------------------


def test_all_11_m3_columns_present(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        cols = _canonical_columns(conn)
    finally:
        conn.close()
    for col in NEW_M3_COLUMNS:
        assert col in cols, f"Expected M3 column '{col}' not found on canonical_postings"


# ---------------------------------------------------------------------------
# Index presence
# ---------------------------------------------------------------------------


def test_m3_sort_index_exists(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?;",
            (NEW_M3_INDEX,),
        ).fetchall()
    finally:
        conn.close()
    assert rows, f"Expected index '{NEW_M3_INDEX}' not found in sqlite_master"


# ---------------------------------------------------------------------------
# CHECK constraints
# ---------------------------------------------------------------------------


def test_fit_score_rejects_zero(tmp_db):
    """fit_score CHECK (BETWEEN 1 AND 5) must reject 0."""
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        _insert_minimal_canonical(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE canonical_postings SET fit_score = 0 WHERE canonical_id = 1;"
            )
            conn.commit()
        conn.rollback()
    finally:
        conn.close()


def test_fit_score_rejects_six(tmp_db):
    """fit_score CHECK (BETWEEN 1 AND 5) must reject 6."""
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        _insert_minimal_canonical(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE canonical_postings SET fit_score = 6 WHERE canonical_id = 1;"
            )
            conn.commit()
        conn.rollback()
    finally:
        conn.close()


def test_fit_score_accepts_valid_range(tmp_db):
    """fit_score must accept 1 through 5 without error."""
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        _insert_minimal_canonical(conn)
        for score in range(1, 6):
            conn.execute(
                "UPDATE canonical_postings SET fit_score = ? WHERE canonical_id = 1;",
                (score,),
            )
            conn.commit()
    finally:
        conn.close()


def test_fit_score_accepts_null(tmp_db):
    """fit_score NULL is allowed (column is nullable)."""
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        _insert_minimal_canonical(conn)
        conn.execute("UPDATE canonical_postings SET fit_score = NULL WHERE canonical_id = 1;")
        conn.commit()
    finally:
        conn.close()


def test_citizenship_requirement_rejects_invalid(tmp_db):
    """citizenship_requirement CHECK must reject values outside the 3-state enum."""
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        _insert_minimal_canonical(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE canonical_postings SET citizenship_requirement = 'unknown' "
                "WHERE canonical_id = 1;"
            )
            conn.commit()
        conn.rollback()
    finally:
        conn.close()


def test_citizenship_requirement_accepts_valid_values(tmp_db):
    """citizenship_requirement must accept all three valid enum values."""
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        _insert_minimal_canonical(conn)
        for val in ("required", "preferred", "not_mentioned"):
            conn.execute(
                "UPDATE canonical_postings SET citizenship_requirement = ? WHERE canonical_id = 1;",
                (val,),
            )
            conn.commit()
    finally:
        conn.close()


def test_can_hire_in_canada_rejects_maybe(tmp_db):
    """can_hire_in_canada CHECK must reject 'maybe'."""
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        _insert_minimal_canonical(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE canonical_postings SET can_hire_in_canada = 'maybe' "
                "WHERE canonical_id = 1;"
            )
            conn.commit()
        conn.rollback()
    finally:
        conn.close()


def test_can_hire_in_canada_accepts_valid_values(tmp_db):
    """can_hire_in_canada must accept all four valid enum values."""
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        _insert_minimal_canonical(conn)
        for val in ("yes", "likely", "no", "unclear"):
            conn.execute(
                "UPDATE canonical_postings SET can_hire_in_canada = ? WHERE canonical_id = 1;",
                (val,),
            )
            conn.commit()
    finally:
        conn.close()


def test_industry_rejects_invalid_sector(tmp_db):
    """industry CHECK must reject values not in the 16-sector taxonomy."""
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        _insert_minimal_canonical(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE canonical_postings SET industry = 'Invalid Sector' WHERE canonical_id = 1;"
            )
            conn.commit()
        conn.rollback()
    finally:
        conn.close()


def test_industry_accepts_all_16_sectors(tmp_db):
    """industry must accept all 16 valid taxonomy values."""
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        _insert_minimal_canonical(conn)
        for sector in _VALID_INDUSTRIES:
            conn.execute(
                "UPDATE canonical_postings SET industry = ? WHERE canonical_id = 1;",
                (sector,),
            )
            conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# is_filtered default
# ---------------------------------------------------------------------------


def test_is_filtered_defaults_to_zero(tmp_db):
    """is_filtered must default to 0 (NOT NULL DEFAULT 0) when not specified."""
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        _insert_minimal_canonical(conn)
        row = conn.execute(
            "SELECT is_filtered FROM canonical_postings WHERE canonical_id = 1;"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == 0, f"Expected is_filtered=0, got {row[0]}"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_m3_migration_is_idempotent(tmp_path):
    """Running init_db twice on the same DB raises no errors and causes no schema drift."""
    db_path = tmp_path / "idempotent_m3.db"

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        before_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(canonical_postings);").fetchall()
        }
        before_indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index';"
            ).fetchall()
        }
    finally:
        conn.close()

    # Second run — must not raise
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        after_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(canonical_postings);").fetchall()
        }
        after_indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index';"
            ).fetchall()
        }
    finally:
        conn.close()

    assert after_cols == before_cols, "Column set changed after re-init"
    assert after_indexes == before_indexes, "Index set changed after re-init"
