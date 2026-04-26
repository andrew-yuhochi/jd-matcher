"""
Tests for C27 — Ingest Report CLI (AC #6, #7, #8, #9, #10).

Covers:
  AC6 — default markdown output with all columns + aggregate row
  AC7 — --since YYYY-MM-DD filters correctly
  AC8 — --source X filters correctly
  AC9 — --format csv outputs valid CSV parseable by csv.DictReader
  AC10 — aggregate totals match column sums
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.db.email_ingest_log import insert_email_log, update_url_counts, increment_hydration
from jd_matcher.report import cmd_ingest, _emit_markdown, _emit_csv, query_email_ingest_log

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


def _seed_rows(db_path: Path, rows: list[dict]) -> None:
    """Seed email_ingest_log with pre-built row dicts."""
    for row in rows:
        now = datetime.now(timezone.utc)
        insert_email_log(
            gmail_message_id=row["gmail_message_id"],
            source=row["source"],
            sender=row.get("sender", "test@test.com"),
            subject=row.get("subject", "Test Subject"),
            received_at=row.get("received_at", now),
            pipeline_run_id=row.get("pipeline_run_id", "run-001"),
            db_path=db_path,
        )
        update_url_counts(
            gmail_message_id=row["gmail_message_id"],
            urls_extracted_count=row.get("urls_extracted_count", 0),
            urls_new_count=row.get("urls_new_count", 0),
            postings_created_count=row.get("postings_created_count", 0),
            db_path=db_path,
        )
        for _ in range(row.get("postings_hydrated_count", 0)):
            increment_hydration(gmail_message_id=row["gmail_message_id"], success=True, db_path=db_path)
        for _ in range(row.get("postings_hydration_failed_count", 0)):
            increment_hydration(gmail_message_id=row["gmail_message_id"], success=False, db_path=db_path)


_SAMPLE_ROWS = [
    {
        "gmail_message_id": "msg-li-001",
        "source": "linkedin",
        "sender": "jobalerts@linkedin.com",
        "subject": "5 new jobs for Data Scientist in Vancouver",
        "received_at": datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc),
        "pipeline_run_id": "run-001",
        "urls_extracted_count": 5,
        "urls_new_count": 5,
        "postings_created_count": 5,
        "postings_hydrated_count": 4,
        "postings_hydration_failed_count": 1,
    },
    {
        "gmail_message_id": "msg-li-002",
        "source": "linkedin",
        "sender": "jobalerts@linkedin.com",
        "subject": "3 new jobs for ML Engineer in Canada",
        "received_at": datetime(2026, 4, 21, 9, 0, 0, tzinfo=timezone.utc),
        "pipeline_run_id": "run-001",
        "urls_extracted_count": 3,
        "urls_new_count": 2,
        "postings_created_count": 2,
        "postings_hydrated_count": 2,
        "postings_hydration_failed_count": 0,
    },
    {
        "gmail_message_id": "msg-in-001",
        "source": "indeed",
        "sender": "alert@indeed.com",
        "subject": "Data Scientist jobs in Vancouver",
        "received_at": datetime(2026, 4, 19, 14, 0, 0, tzinfo=timezone.utc),
        "pipeline_run_id": "run-001",
        "urls_extracted_count": 8,
        "urls_new_count": 3,
        "postings_created_count": 3,
        "postings_hydrated_count": 3,
        "postings_hydration_failed_count": 0,
    },
    {
        "gmail_message_id": "msg-in-002",
        "source": "indeed",
        "sender": "alert@indeed.com",
        "subject": "New jobs matching your alert",
        "received_at": datetime(2026, 4, 18, 8, 0, 0, tzinfo=timezone.utc),
        "pipeline_run_id": "run-001",
        "urls_extracted_count": 6,
        "urls_new_count": 1,
        "postings_created_count": 1,
        "postings_hydrated_count": 0,
        "postings_hydration_failed_count": 1,
    },
    {
        "gmail_message_id": "msg-li-003",
        "source": "linkedin",
        "sender": "jobalerts@linkedin.com",
        "subject": "Senior Data Analyst opportunity",
        "received_at": datetime(2026, 4, 22, 11, 0, 0, tzinfo=timezone.utc),
        "pipeline_run_id": "run-002",
        "urls_extracted_count": 2,
        "urls_new_count": 2,
        "postings_created_count": 2,
        "postings_hydrated_count": 1,
        "postings_hydration_failed_count": 1,
    },
]


# ---------------------------------------------------------------------------
# Helper — capture stdout
# ---------------------------------------------------------------------------


class _ArgStub:
    def __init__(self, **kwargs):
        self.since = kwargs.get("since", None)
        self.source = kwargs.get("source", None)
        self.format = kwargs.get("format", "markdown")
        self.db = kwargs.get("db", None)


# ---------------------------------------------------------------------------
# AC6 — default markdown output renders all rows + aggregate
# ---------------------------------------------------------------------------


class TestMarkdownOutput:
    def test_markdown_contains_header_columns(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(db_path=test_db)
        _emit_markdown(rows)
        out = capsys.readouterr().out
        for col in ["Date", "Source", "Subject", "URLs", "New", "Posts", "Hydrated", "Failed"]:
            assert col in out, f"Column '{col}' missing from markdown output"

    def test_markdown_has_correct_row_count(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(db_path=test_db)
        _emit_markdown(rows)
        out = capsys.readouterr().out
        # Each data row starts with "| "
        data_lines = [ln for ln in out.splitlines() if ln.startswith("|") and "---" not in ln and "Date" not in ln and "TOTAL" not in ln]
        assert len(data_lines) == len(_SAMPLE_ROWS), (
            f"Expected {len(_SAMPLE_ROWS)} data rows, got {len(data_lines)}"
        )

    def test_markdown_has_aggregate_row(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(db_path=test_db)
        _emit_markdown(rows)
        out = capsys.readouterr().out
        assert "TOTAL" in out, "Aggregate/totals row missing from markdown output"

    def test_markdown_aggregate_totals_correct(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(db_path=test_db)
        _emit_markdown(rows)
        out = capsys.readouterr().out

        expected_urls = sum(r["urls_extracted_count"] for r in _SAMPLE_ROWS)
        expected_new = sum(r["urls_new_count"] for r in _SAMPLE_ROWS)
        expected_hydrated = sum(r["postings_hydrated_count"] for r in _SAMPLE_ROWS)
        expected_failed = sum(r["postings_hydration_failed_count"] for r in _SAMPLE_ROWS)

        assert str(expected_urls) in out, f"Total URLs ({expected_urls}) missing from output"
        assert str(expected_new) in out, f"Total New ({expected_new}) missing from output"
        assert str(expected_hydrated) in out, f"Total Hydrated ({expected_hydrated}) missing from output"
        assert str(expected_failed) in out, f"Total Failed ({expected_failed}) missing from output"

    def test_markdown_subject_truncated_to_40_chars(self, test_db: Path, capsys) -> None:
        long_subject_row = [{
            "gmail_message_id": "msg-long-subj",
            "source": "linkedin",
            "subject": "A" * 60,
            "received_at": datetime(2026, 4, 20, tzinfo=timezone.utc),
            "pipeline_run_id": "run-001",
        }]
        _seed_rows(test_db, long_subject_row)
        rows = query_email_ingest_log(db_path=test_db)
        _emit_markdown(rows)
        out = capsys.readouterr().out
        # The 60-char subject must be truncated to 40 in the output
        assert "A" * 60 not in out, "Subject was not truncated to 40 chars"
        assert "A" * 40 in out, "Truncated 40-char subject not found"


# ---------------------------------------------------------------------------
# AC7 — --since filter
# ---------------------------------------------------------------------------


class TestSinceFilter:
    def test_since_filter_excludes_older_rows(self, test_db: Path) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        # Rows with received_at >= 2026-04-21
        rows = query_email_ingest_log(since="2026-04-21", db_path=test_db)
        for row in rows:
            date_part = row["received_at"][:10]
            assert date_part >= "2026-04-21", (
                f"Row {row['gmail_message_id']} received_at={date_part} < since=2026-04-21"
            )

    def test_since_filter_row_count(self, test_db: Path) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        # In _SAMPLE_ROWS: msg-li-002 (Apr 21), msg-li-003 (Apr 22) >= Apr 21.
        rows = query_email_ingest_log(since="2026-04-21", db_path=test_db)
        expected = [r for r in _SAMPLE_ROWS if r["received_at"] >= datetime(2026, 4, 21, tzinfo=timezone.utc)]
        assert len(rows) == len(expected), (
            f"Expected {len(expected)} rows since 2026-04-21, got {len(rows)}"
        )

    def test_since_no_filter_returns_all(self, test_db: Path) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(db_path=test_db)
        assert len(rows) == len(_SAMPLE_ROWS)


# ---------------------------------------------------------------------------
# AC8 — --source filter
# ---------------------------------------------------------------------------


class TestSourceFilter:
    def test_source_filter_linkedin_only(self, test_db: Path) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(source="linkedin", db_path=test_db)
        expected_count = sum(1 for r in _SAMPLE_ROWS if r["source"] == "linkedin")
        assert len(rows) == expected_count
        for row in rows:
            assert row["source"] == "linkedin"

    def test_source_filter_indeed_only(self, test_db: Path) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(source="indeed", db_path=test_db)
        expected_count = sum(1 for r in _SAMPLE_ROWS if r["source"] == "indeed")
        assert len(rows) == expected_count
        for row in rows:
            assert row["source"] == "indeed"

    def test_source_filter_combined_with_since(self, test_db: Path) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(since="2026-04-20", source="linkedin", db_path=test_db)
        expected = [
            r for r in _SAMPLE_ROWS
            if r["source"] == "linkedin" and r["received_at"] >= datetime(2026, 4, 20, tzinfo=timezone.utc)
        ]
        assert len(rows) == len(expected)


# ---------------------------------------------------------------------------
# AC9 — --format csv outputs valid CSV parseable by csv.DictReader
# ---------------------------------------------------------------------------


class TestCsvOutput:
    def test_csv_parseable_by_dictreader(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(db_path=test_db)
        _emit_csv(rows)
        out = capsys.readouterr().out

        reader = csv.DictReader(io.StringIO(out))
        parsed = list(reader)
        assert len(parsed) > 0, "csv.DictReader parsed zero rows"

    def test_csv_has_required_columns(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(db_path=test_db)
        _emit_csv(rows)
        out = capsys.readouterr().out

        reader = csv.DictReader(io.StringIO(out))
        assert reader.fieldnames is not None
        for col in ["Date", "Source", "Subject", "URLs", "New", "Posts", "Hydrated", "Failed"]:
            assert col in reader.fieldnames, f"Column '{col}' missing from CSV"

    def test_csv_data_row_count(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(db_path=test_db)
        _emit_csv(rows)
        out = capsys.readouterr().out

        reader = csv.DictReader(io.StringIO(out))
        parsed = list(reader)
        # N data rows + 1 TOTAL row
        assert len(parsed) == len(_SAMPLE_ROWS) + 1, (
            f"Expected {len(_SAMPLE_ROWS) + 1} CSV rows (data + TOTAL), got {len(parsed)}"
        )

    def test_csv_totals_row_present(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(db_path=test_db)
        _emit_csv(rows)
        out = capsys.readouterr().out

        reader = csv.DictReader(io.StringIO(out))
        parsed = list(reader)
        assert any(row.get("Subject") == "TOTAL" for row in parsed), (
            "TOTAL row not found in CSV output"
        )

    def test_csv_totals_match_column_sums(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        rows = query_email_ingest_log(db_path=test_db)
        _emit_csv(rows)
        out = capsys.readouterr().out

        reader = csv.DictReader(io.StringIO(out))
        parsed = list(reader)
        total_row = next(r for r in parsed if r.get("Subject") == "TOTAL")
        data_rows = [r for r in parsed if r.get("Subject") != "TOTAL"]

        assert int(total_row["URLs"]) == sum(int(r["URLs"]) for r in data_rows)
        assert int(total_row["New"]) == sum(int(r["New"]) for r in data_rows)
        assert int(total_row["Hydrated"]) == sum(int(r["Hydrated"]) for r in data_rows)
        assert int(total_row["Failed"]) == sum(int(r["Failed"]) for r in data_rows)


# ---------------------------------------------------------------------------
# AC6/AC10 via cmd_ingest end-to-end
# ---------------------------------------------------------------------------


class TestCmdIngest:
    def test_cmd_ingest_default_markdown(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        args = _ArgStub(db=str(test_db))
        cmd_ingest(args)
        out = capsys.readouterr().out
        assert "Date" in out
        assert "TOTAL" in out

    def test_cmd_ingest_csv_format(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        args = _ArgStub(db=str(test_db), format="csv")
        cmd_ingest(args)
        out = capsys.readouterr().out
        reader = csv.DictReader(io.StringIO(out))
        parsed = list(reader)
        assert len(parsed) > 0

    def test_cmd_ingest_since_filter(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        args = _ArgStub(db=str(test_db), since="2026-04-21")
        cmd_ingest(args)
        out = capsys.readouterr().out
        # Only rows from Apr 21+ should appear; Apr 18, 19, 20 excluded.
        assert "2026-04-18" not in out
        assert "2026-04-19" not in out
        assert "2026-04-20" not in out

    def test_cmd_ingest_source_filter(self, test_db: Path, capsys) -> None:
        _seed_rows(test_db, _SAMPLE_ROWS)
        args = _ArgStub(db=str(test_db), source="indeed")
        cmd_ingest(args)
        out = capsys.readouterr().out
        # linkedin rows should not appear
        assert "jobalerts@linkedin.com" not in out or "indeed" in out

    def test_cmd_ingest_empty_table_renders_header_only(self, test_db: Path, capsys) -> None:
        args = _ArgStub(db=str(test_db))
        cmd_ingest(args)
        out = capsys.readouterr().out
        assert "Date" in out
        assert "TOTAL" in out
