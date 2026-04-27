"""
Filter correctness validation CLI (TASK-M2-004 Phase A).

Runs filter_title() against all postings in the local DB and produces a
Markdown report that lists dropped vs passed postings for user review.

Usage:
    .venv/bin/python -m jd_matcher.filter.validate [options]

Options:
    --db <path>          SQLite DB path (default: ~/.jd-matcher/jd-matcher.db)
    --config <path>      title_filters.yaml path (default: config/title_filters.yaml)
    --report-out <path>  Report destination (default: docs/poc/quality-logs/TASK-M2-004-validation-report.md)
    --print-summary      Print the summary block to stdout in addition to writing the report
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from jd_matcher.filter.title_filter import FilterDecision, TitleFilters, filter_title, load_filters

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".jd-matcher" / "jd-matcher.db"
_DEFAULT_CONFIG = Path(__file__).parents[3] / "config" / "title_filters.yaml"
_DEFAULT_REPORT = (
    Path(__file__).parents[3] / "docs" / "poc" / "quality-logs" / "TASK-M2-004-validation-report.md"
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PostingRow:
    id: int
    canonical_title: str
    canonical_company: str
    canonical_location: str
    sources: str  # comma-separated list from GROUP_CONCAT


@dataclass
class DropRecord:
    posting: PostingRow
    decision: FilterDecision


@dataclass
class PassRecord:
    posting: PostingRow


@dataclass
class ValidationSummary:
    total_in_db: int
    skipped: int
    total_analyzed: int
    dropped: list[DropRecord] = field(default_factory=list)
    passed: list[PassRecord] = field(default_factory=list)

    @property
    def drop_count(self) -> int:
        return len(self.dropped)

    @property
    def pass_count(self) -> int:
        return len(self.passed)


# ---------------------------------------------------------------------------
# DB query
# ---------------------------------------------------------------------------


def _fetch_postings(db_path: Path) -> tuple[list[PostingRow], int]:
    """Return (rows_with_title, skipped_count) from the postings table.

    Joins posting_sources to surface the source column. Each posting may have
    multiple source rows; GROUP_CONCAT(DISTINCT source) collapses them.
    """
    query = """
        SELECT
            p.id,
            p.canonical_title,
            COALESCE(p.canonical_company, '') AS canonical_company,
            COALESCE(p.canonical_location, '') AS canonical_location,
            GROUP_CONCAT(DISTINCT ps.source) AS sources
        FROM postings p
        JOIN posting_sources ps ON p.id = ps.posting_id
        GROUP BY p.id
        ORDER BY p.id
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()

    valid: list[PostingRow] = []
    skipped = 0
    for row in rows:
        title = row["canonical_title"]
        if not title or not title.strip():
            skipped += 1
            continue
        valid.append(
            PostingRow(
                id=row["id"],
                canonical_title=title,
                canonical_company=row["canonical_company"],
                canonical_location=row["canonical_location"],
                sources=row["sources"] or "",
            )
        )
    return valid, skipped


# ---------------------------------------------------------------------------
# Core validation logic
# ---------------------------------------------------------------------------


def run_validation(
    db_path: Path = _DEFAULT_DB,
    config_path: Path = _DEFAULT_CONFIG,
) -> ValidationSummary:
    """Run filter_title() against all DB postings and return a ValidationSummary."""
    postings, skipped = _fetch_postings(db_path)
    filters: TitleFilters = load_filters(config_path)

    dropped: list[DropRecord] = []
    passed: list[PassRecord] = []

    for posting in postings:
        decision: FilterDecision = filter_title(posting.canonical_title, filters=filters)
        if decision.action == "drop":
            dropped.append(DropRecord(posting=posting, decision=decision))
        else:
            passed.append(PassRecord(posting=posting))

    # Sort passed list alphabetically by title for easier scanning
    passed.sort(key=lambda r: r.posting.canonical_title.lower())

    return ValidationSummary(
        total_in_db=len(postings) + skipped,
        skipped=skipped,
        total_analyzed=len(postings),
        dropped=dropped,
        passed=passed,
    )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _config_sha(config_path: Path) -> str:
    """Return short git SHA of the config file, or 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1", "--", str(config_path)],
            capture_output=True,
            text=True,
            cwd=config_path.parent,
        )
        line = result.stdout.strip()
        return line.split()[0] if line else "unknown"
    except Exception:
        return "unknown"


def _pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{numerator / denominator * 100:.1f}%"


def render_report(
    summary: ValidationSummary,
    db_path: Path,
    config_path: Path,
    iteration: int = 1,
) -> str:
    """Render the Markdown validation report as a string."""
    date_str = datetime.date.today().isoformat()
    sha = _config_sha(config_path)
    n = summary.total_analyzed
    d = summary.drop_count
    p = summary.pass_count

    lines: list[str] = []

    lines.append(f"# TASK-M2-004 — Filter Validation Report (Iteration {iteration})")
    lines.append("")
    lines.append(f"Date: {date_str}")
    lines.append(f"Source DB: {db_path}")
    lines.append(
        f"Total postings analyzed: {n}  "
        f"(skipped {summary.skipped} with empty canonical_title)"
    )
    lines.append(f"Config snapshot: config/title_filters.yaml @ commit {sha}")
    lines.append("")

    # --- Summary table ---
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric            | Count | % of analyzed |")
    lines.append("|-------------------|-------|---------------|")
    lines.append(f"| Total analyzed    | {n}   | 100%          |")
    lines.append(f"| Filtered (drop)   | {d}   | {_pct(d, n)}       |")
    lines.append(f"| Passed (pass)     | {p}   | {_pct(p, n)}       |")
    lines.append("")

    # --- Dropped postings ---
    lines.append("## Filtered postings — for user review (label correct-drop or FALSE POSITIVE)")
    lines.append("")
    lines.append("| ID | Source | Title | Company | Location | Matched Pattern |")
    lines.append("|----|--------|-------|---------|----------|-----------------|")
    for rec in summary.dropped:
        posting = rec.posting
        pattern_display = f"`{rec.decision.matched_pattern}`" if rec.decision.matched_pattern else "_(none)_"
        lines.append(
            f"| {posting.id} | {posting.sources} | {posting.canonical_title} "
            f"| {posting.canonical_company} | {posting.canonical_location} "
            f"| {pattern_display} |"
        )
    lines.append("")

    # --- Passed postings ---
    lines.append("## Passed postings — for user spot-check (label correct-pass or FALSE NEGATIVE)")
    lines.append("")
    lines.append("Sorted by title alphabetically for scanning.")
    lines.append("")
    lines.append("| ID | Source | Title | Company | Location |")
    lines.append("|----|--------|-------|---------|----------|")
    for rec in summary.passed:
        posting = rec.posting
        lines.append(
            f"| {posting.id} | {posting.sources} | {posting.canonical_title} "
            f"| {posting.canonical_company} | {posting.canonical_location} |"
        )
    lines.append("")

    # --- Instructions ---
    lines.append("## How to label (instructions for the user)")
    lines.append("")
    lines.append("For each row above, mentally tag:")
    lines.append("- **Filtered**: correct-drop  /  FALSE POSITIVE (legit job we lost)")
    lines.append("- **Passed**:   correct-pass  /  FALSE NEGATIVE (irrelevant job that slipped through)")
    lines.append("")
    lines.append("Then we tune `config/title_filters.yaml`:")
    lines.append("- False positives → add allow override pattern, OR narrow the deny pattern")
    lines.append("- False negatives → add new deny pattern")
    lines.append("")
    lines.append(
        "Re-run `.venv/bin/python -m jd_matcher.filter.validate` after each YAML edit. "
        "Iterate until:"
    )
    lines.append(
        "- Precision >= 95%  (filtered \\ false_positives) / filtered  >= 0.95"
    )
    lines.append(
        "- Recall >= 98%      (passed \\ false_negatives) / total_legit >= 0.98"
    )
    lines.append("")

    return "\n".join(lines)


def render_summary_block(summary: ValidationSummary) -> str:
    """Render the summary numbers as a short human-readable block for stdout."""
    n = summary.total_analyzed
    d = summary.drop_count
    p = summary.pass_count
    lines = [
        "=== Filter Validation Summary ===",
        f"Total in DB (non-null title): {n + summary.skipped}",
        f"  Skipped (empty title):      {summary.skipped}",
        f"  Analyzed:                   {n}",
        f"  Filtered (drop):            {d}  ({_pct(d, n)})",
        f"  Passed (pass):              {p}  ({_pct(p, n)})",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the C19 title filter against all DB postings and produce a "
            "Markdown report for user review."
        )
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_DEFAULT_DB,
        help=f"SQLite DB path (default: {_DEFAULT_DB})",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_DEFAULT_CONFIG,
        help="Path to title_filters.yaml",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=_DEFAULT_REPORT,
        help=f"Report output path (default: {_DEFAULT_REPORT})",
    )
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Also print the summary block to stdout",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    summary = run_validation(db_path=args.db, config_path=args.config)
    report = render_report(summary, db_path=args.db, config_path=args.config)

    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(report, encoding="utf-8")
    logger.info("Report written to %s", args.report_out)

    if args.print_summary:
        print(render_summary_block(summary))
    print(f"Report written to: {args.report_out}")


if __name__ == "__main__":
    _main()
