"""
Tests for TASK-M2-004 — filter correctness validation CLI.

Coverage:
  - ValidationSummary counts (total, dropped, passed) on seeded tmp DB
  - Correct IDs in dropped / passed lists
  - CLI end-to-end: produces non-empty report file against tmp DB
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.filter.validate import (
    ValidationSummary,
    render_report,
    run_validation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).parents[2] / "config" / "title_filters.yaml"


def _seed_db(db_path: Path) -> dict[str, int]:
    """Insert 5 test postings; return {title: id} mapping.

    Expected filter outcomes with the default config:
      DROP:
        "Director of Engineering"   → matches \bDirector\b deny
        "QA Engineer"               → matches \bQA (Engineer|…)\b deny
        "Senior Full-Stack Developer" → matches \bFull.?Stack (Engineer|Developer)\b deny
      PASS:
        "Senior Data Scientist"     → no deny match
        "Machine Learning Engineer" → no deny match
    """
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        titles = [
            ("Director of Engineering", "Acme Corp", "Vancouver"),
            ("QA Engineer", "Beta Inc", "Toronto"),
            ("Senior Full-Stack Developer", "Gamma Ltd", "Remote"),
            ("Senior Data Scientist", "Delta AI", "Vancouver"),
            ("Machine Learning Engineer", "Epsilon ML", "Remote"),
        ]
        id_map: dict[str, int] = {}
        for title, company, location in titles:
            cur = conn.execute(
                """
                INSERT INTO postings
                    (user_id, canonical_title, canonical_company, canonical_location,
                     hydration_status, first_seen, last_seen)
                VALUES ('default', ?, ?, ?, 'complete', datetime('now'), datetime('now'))
                """,
                (title, company, location),
            )
            posting_id = cur.lastrowid
            id_map[title] = posting_id
            conn.execute(
                """
                INSERT INTO posting_sources
                    (posting_id, user_id, source, source_url, source_first_seen)
                VALUES (?, 'default', 'test_source', 'http://example.com', datetime('now'))
                """,
                (posting_id,),
            )
        conn.commit()
    finally:
        conn.close()
    return id_map


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_validation_summary_counts(tmp_path: Path) -> None:
    """ValidationSummary has correct total/dropped/passed counts."""
    db_path = tmp_path / "test.db"
    _seed_db(db_path)

    summary: ValidationSummary = run_validation(db_path=db_path, config_path=CONFIG_PATH)

    assert summary.total_analyzed == 5
    assert summary.skipped == 0
    assert summary.drop_count == 3
    assert summary.pass_count == 2


def test_validation_dropped_ids(tmp_path: Path) -> None:
    """The correct posting IDs appear in the dropped list."""
    db_path = tmp_path / "test.db"
    id_map = _seed_db(db_path)

    summary = run_validation(db_path=db_path, config_path=CONFIG_PATH)

    dropped_ids = {rec.posting.id for rec in summary.dropped}
    assert id_map["Director of Engineering"] in dropped_ids
    assert id_map["QA Engineer"] in dropped_ids
    assert id_map["Senior Full-Stack Developer"] in dropped_ids


def test_validation_passed_ids(tmp_path: Path) -> None:
    """The correct posting IDs appear in the passed list."""
    db_path = tmp_path / "test.db"
    id_map = _seed_db(db_path)

    summary = run_validation(db_path=db_path, config_path=CONFIG_PATH)

    passed_ids = {rec.posting.id for rec in summary.passed}
    assert id_map["Senior Data Scientist"] in passed_ids
    assert id_map["Machine Learning Engineer"] in passed_ids


def test_validation_passed_sorted_alphabetically(tmp_path: Path) -> None:
    """Passed list is sorted by title alphabetically."""
    db_path = tmp_path / "test.db"
    _seed_db(db_path)

    summary = run_validation(db_path=db_path, config_path=CONFIG_PATH)

    titles = [rec.posting.canonical_title.lower() for rec in summary.passed]
    assert titles == sorted(titles)


def test_cli_produces_report(tmp_path: Path) -> None:
    """CLI end-to-end: writing to a tmp report path produces a non-empty file."""
    db_path = tmp_path / "test.db"
    _seed_db(db_path)
    report_path = tmp_path / "report.md"

    summary = run_validation(db_path=db_path, config_path=CONFIG_PATH)
    report_text = render_report(summary, db_path=db_path, config_path=CONFIG_PATH)
    report_path.write_text(report_text, encoding="utf-8")

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert len(content) > 200
    assert "## Summary" in content
    assert "## Filtered postings" in content
    assert "## Passed postings" in content


def test_cli_report_contains_drop_titles(tmp_path: Path) -> None:
    """Report text contains the dropped posting titles."""
    db_path = tmp_path / "test.db"
    _seed_db(db_path)
    report_path = tmp_path / "report.md"

    summary = run_validation(db_path=db_path, config_path=CONFIG_PATH)
    report_text = render_report(summary, db_path=db_path, config_path=CONFIG_PATH)
    report_path.write_text(report_text, encoding="utf-8")

    content = report_path.read_text(encoding="utf-8")
    assert "Director of Engineering" in content
    assert "QA Engineer" in content
    assert "Senior Full-Stack Developer" in content


def test_cli_skips_empty_title(tmp_path: Path) -> None:
    """Postings with NULL/empty canonical_title are skipped from analysis."""
    db_path = tmp_path / "test.db"
    _seed_db(db_path)

    # Insert an extra posting with NULL title
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        cur = conn.execute(
            """
            INSERT INTO postings
                (user_id, canonical_title, canonical_company, canonical_location,
                 hydration_status, first_seen, last_seen)
            VALUES ('default', NULL, 'NullCo', 'Nowhere', 'complete', datetime('now'), datetime('now'))
            """
        )
        null_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO posting_sources
                (posting_id, user_id, source, source_url, source_first_seen)
            VALUES (?, 'default', 'test_source', 'http://example.com', datetime('now'))
            """,
            (null_id,),
        )
        conn.commit()
    finally:
        conn.close()

    summary = run_validation(db_path=db_path, config_path=CONFIG_PATH)

    assert summary.skipped == 1
    assert summary.total_analyzed == 5  # original 5, NULL row excluded
