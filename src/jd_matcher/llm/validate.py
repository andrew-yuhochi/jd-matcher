"""TASK-M2-006 Calibration Phase A — Extraction Validation CLI.

Runs extract_canonical against all C19-passed postings in the real DB
and produces a Markdown report for per-field user labeling.

Usage:
    .venv/bin/python -m jd_matcher.llm.validate [--db PATH] [--report-out PATH]
                                                  [--limit N] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import textwrap
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from jd_matcher.filter.title_filter import filter_title
from jd_matcher.llm.extract import (
    CanonicalExtraction,
    ExtractionParseError,
    PostingRow,
    extract_canonical,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"
_DEFAULT_REPORT_PATH = (
    Path(__file__).parents[3]
    / "docs"
    / "poc"
    / "quality-logs"
    / "TASK-M2-006-validation-report.md"
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PostingRecord:
    """Full row needed by the validator — includes source for the report."""

    id: int
    canonical_title: str | None
    canonical_company: str | None
    canonical_location: str | None
    full_jd: str
    source: str | None  # from posting_sources (first source found)


@dataclass
class ExtractionResult:
    posting: PostingRecord
    extraction: CanonicalExtraction | None
    cache_hit: bool
    failed: bool
    failure_reason: str | None = None


@dataclass
class RunStats:
    analyzed: int = 0
    success: int = 0
    failures: list[tuple[int, str]] = field(default_factory=list)
    cache_hits: int = 0
    new_api_calls: int = 0
    run_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _fetch_all_postings(db_path: Path) -> list[PostingRecord]:
    """Return all postings with non-empty full_jd, joined with first source."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                p.id,
                p.canonical_title,
                p.canonical_company,
                p.canonical_location,
                p.full_jd,
                (
                    SELECT ps.source
                    FROM posting_sources ps
                    WHERE ps.posting_id = p.id
                    ORDER BY ps.id ASC
                    LIMIT 1
                ) AS source
            FROM postings p
            WHERE p.full_jd IS NOT NULL AND p.full_jd != ''
            ORDER BY p.id ASC
            """
        ).fetchall()
        return [
            PostingRecord(
                id=r["id"],
                canonical_title=r["canonical_title"],
                canonical_company=r["canonical_company"],
                canonical_location=r["canonical_location"],
                full_jd=r["full_jd"],
                source=r["source"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def _ledger_cost_since(db_path: Path, posting_ids: list[int]) -> tuple[float, int, int]:
    """Return (run_cost_usd, new_api_calls, cache_hits) for this batch of postings."""
    if not posting_ids:
        return 0.0, 0, 0
    placeholders = ",".join("?" * len(posting_ids))
    str_ids = [str(pid) for pid in posting_ids]
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT status, cost_usd FROM llm_call_ledger WHERE posting_id IN ({placeholders})",
            str_ids,
        ).fetchall()
    finally:
        conn.close()

    # Compute per-run cost from the ledger rows we just wrote.
    # We only count rows from this invocation, so we track them via posting_ids.
    # The ledger may have prior rows (e.g. posting 91 from the M2-006 demo);
    # we include all rows for these IDs as they reflect total spend on this batch.
    run_cost = sum(r[1] for r in rows if r[0] == "success")
    new_calls = sum(1 for r in rows if r[0] == "success")
    hits = sum(1 for r in rows if r[0] == "cache_hit")
    return run_cost, new_calls, hits


def _total_ledger_cost(db_path: Path) -> float:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM llm_call_ledger WHERE status = 'success'"
        ).fetchone()
        return row[0] if row else 0.0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Filter helper — apply C19 in-memory
# ---------------------------------------------------------------------------


def _apply_c19_filter(postings: list[PostingRecord]) -> list[PostingRecord]:
    """Return only those postings whose canonical_title passes the C19 filter."""
    passing = []
    for p in postings:
        title = p.canonical_title or ""
        decision = filter_title(title)
        if decision.action == "pass":
            passing.append(p)
    return passing


# ---------------------------------------------------------------------------
# Core extraction loop
# ---------------------------------------------------------------------------


def run_validation(
    db_path: Path,
    limit: int | None = None,
    dry_run: bool = False,
) -> tuple[list[ExtractionResult], RunStats]:
    """Run extract_canonical for all C19-passed postings.

    Returns (results, stats).  In dry_run mode results is empty and stats
    contains only the counts of what WOULD be extracted.
    """
    all_postings = _fetch_all_postings(db_path)
    passing = _apply_c19_filter(all_postings)

    skipped_count = len(all_postings) - len(passing)
    logger.info(
        "validate: %d total postings with full_jd, %d pass C19 filter, %d dropped",
        len(all_postings),
        len(passing),
        skipped_count,
    )

    if limit is not None:
        passing = passing[:limit]

    if dry_run:
        print(f"DRY RUN — would extract {len(passing)} postings (C19 passed).")
        print(f"  Total postings with full_jd: {len(all_postings)}")
        print(f"  Filtered out by C19: {skipped_count}")
        if limit is not None:
            print(f"  --limit {limit} applied; full C19-pass set would be {len(passing)} (before limit)")
        for p in passing:
            print(f"  ID={p.id:>3}  [{p.source or 'unknown':>20}]  {p.canonical_title}")
        stats = RunStats(analyzed=len(passing))
        return [], stats

    results: list[ExtractionResult] = []
    posting_ids_processed: list[int] = []
    stats = RunStats(analyzed=len(passing))

    for p in passing:
        posting_row = PostingRow(
            id=p.id,
            full_jd=p.full_jd,
            canonical_title=p.canonical_title,
            canonical_company=p.canonical_company,
            canonical_location=p.canonical_location,
        )
        priors: dict[str, str] = {}
        if p.canonical_company:
            priors["company"] = p.canonical_company
        if p.canonical_title:
            priors["title"] = p.canonical_title
        if p.canonical_location:
            priors["location"] = p.canonical_location

        try:
            extraction = extract_canonical(
                posting_row,
                db_path=db_path,
                priors=priors or None,
            )
            stats.success += 1
            results.append(
                ExtractionResult(
                    posting=p,
                    extraction=extraction,
                    cache_hit=False,  # refined below via ledger
                    failed=False,
                )
            )
        except ExtractionParseError as exc:
            logger.error("validate: parse failure for posting %d — %s", p.id, exc)
            stats.failures.append((p.id, str(exc)))
            results.append(
                ExtractionResult(
                    posting=p,
                    extraction=None,
                    cache_hit=False,
                    failed=True,
                    failure_reason=str(exc),
                )
            )
        except Exception as exc:
            logger.error("validate: unexpected failure for posting %d — %s", p.id, exc)
            stats.failures.append((p.id, str(exc)))
            results.append(
                ExtractionResult(
                    posting=p,
                    extraction=None,
                    cache_hit=False,
                    failed=True,
                    failure_reason=str(exc),
                )
            )

        posting_ids_processed.append(p.id)

    # Reconcile cache vs. new-call counts from the ledger
    run_cost, new_calls, cache_hits = _ledger_cost_since(db_path, posting_ids_processed)
    stats.run_cost_usd = run_cost
    stats.new_api_calls = new_calls
    stats.cache_hits = cache_hits

    # Back-annotate cache_hit flag on results
    conn = sqlite3.connect(db_path)
    try:
        str_ids = [str(p) for p in posting_ids_processed]
        placeholders = ",".join("?" * len(str_ids))
        cache_id_rows = conn.execute(
            f"SELECT DISTINCT posting_id FROM llm_call_ledger "
            f"WHERE posting_id IN ({placeholders}) AND status = 'cache_hit'",
            str_ids,
        ).fetchall() if str_ids else []
        cache_ids = {r[0] for r in cache_id_rows}
    finally:
        conn.close()

    for r in results:
        if str(r.posting.id) in cache_ids:
            r.cache_hit = True

    return results, stats


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _normalise_source(raw: str | None) -> str:
    """Map raw source strings to display labels."""
    if raw is None:
        return "unknown"
    s = raw.lower()
    if "linkedin" in s:
        return "linkedin"
    if "indeed" in s:
        return "indeed"
    if "jobbank" in s or "job_bank" in s:
        return "jobbank"
    return raw


def _skills_top3(skills: list[str]) -> str:
    return ", ".join(skills[:3]) if skills else "—"


def _summary_excerpt(summary: str, chars: int = 100) -> str:
    excerpt = summary[:chars].replace("\n", " ").strip()
    return f'"{excerpt}..."' if len(summary) > chars else f'"{excerpt}"'


def _email_title(record: PostingRecord) -> str:
    """Use canonical_title as the email subject line (closest proxy)."""
    return record.canonical_title or "—"


def generate_report(
    results: list[ExtractionResult],
    stats: RunStats,
    db_path: Path,
    skipped_empty_jd: int = 0,
) -> str:
    total_cost = _total_ledger_cost(db_path)

    # Sort successful results by company then title for the table
    successful = [r for r in results if not r.failed and r.extraction is not None]
    failed = [r for r in results if r.failed]

    successful_sorted = sorted(
        successful,
        key=lambda r: (
            (r.extraction.canonical_company or "").lower(),
            (r.extraction.canonical_title or "").lower(),
        ),
    )

    lines: list[str] = []
    lines.append("# TASK-M2-006 — Extraction Validation Report (Iteration 1)")
    lines.append("")
    lines.append(f"Date: {date.today().isoformat()}")
    lines.append(f"Source DB: {db_path}")
    lines.append(
        f"C19-passed postings analyzed: {stats.analyzed}"
        + (f"  (skipped {skipped_empty_jd} with empty full_jd)" if skipped_empty_jd else "")
    )
    lines.append(
        f"Cost (this run): ${stats.run_cost_usd:.6f} across {stats.new_api_calls} live API calls "
        f"({stats.cache_hits} cache hits)"
    )
    lines.append(f"Total cost on jd-matcher account to date: ${total_cost:.6f}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Postings analyzed | {stats.analyzed} |")
    lines.append(f"| Successful extractions | {stats.success} |")
    lines.append(f"| Parse failures (3-retry exhausted) | {len(stats.failures)} |")
    lines.append(f"| Cache hits (no API call) | {stats.cache_hits} |")
    lines.append(f"| New API calls | {stats.new_api_calls} |")
    lines.append("")

    if failed:
        lines.append("## Extraction Failures")
        lines.append("")
        for pid, reason in stats.failures:
            short = textwrap.shorten(reason, width=120)
            lines.append(f"- Posting ID {pid}: {short}")
        lines.append("")

    lines.append("## Extractions — full table for user review")
    lines.append("")
    lines.append("Sorted by company alphabetically, then title.")
    lines.append("")
    lines.append(
        "| ID | Source | Email Title | LLM Title | LLM Company | Seniority | "
        "Location | Team | Skills (top 3) | Summary (excerpt) |"
    )
    lines.append(
        "|----|--------|-------------|-----------|-------------|-----------|"
        "----------|------|----------------|-------------------|"
    )

    for r in successful_sorted:
        e = r.extraction
        assert e is not None
        row_cells = [
            str(r.posting.id),
            _normalise_source(r.posting.source),
            _email_title(r.posting),
            e.canonical_title,
            e.canonical_company,
            e.canonical_seniority,
            e.canonical_location,
            e.team_or_department or "NULL",
            _skills_top3(e.top_skills),
            _summary_excerpt(e.role_summary),
        ]
        lines.append("| " + " | ".join(row_cells) + " |")

    lines.append("")
    lines.append("## How to label (instructions for the user)")
    lines.append("")
    lines.append(
        "For a stratified sample of 10–15 rows above (mix of LinkedIn + Indeed, "
        "mix of seniority levels, mix of clear-cut + ambiguous cases), assign per-field labels:"
    )
    lines.append("")
    lines.append("| Field | Label values |")
    lines.append("|-------|--------------|")
    lines.append(
        "| canonical_title | correct / wrong / partial (drop modifier or seniority hint) |"
    )
    lines.append(
        "| canonical_company | correct / wrong / over-stripped "
        "(e.g. `TELUS Digital → TELUS` — division dropped) |"
    )
    lines.append(
        "| canonical_seniority | correct / wrong / borderline (e.g. Lead vs Staff) |"
    )
    lines.append(
        "| canonical_location | correct / wrong / fallback-to-Other "
        "(Other when a real city was discoverable) |"
    )
    lines.append(
        "| team_or_department | correct / wrong / null-when-extractable / "
        "non-null-when-not / too-granular (role-level instead of org-unit) |"
    )
    lines.append("| top_skills | good / OK / poor (list intersection vs your judgment) |")
    lines.append(
        "| role_summary | embedding-suitable (neutral, no marketing) / poor / bad |"
    )
    lines.append("")
    lines.append("Then report counts. We compute per-field precision against:")
    lines.append("")
    lines.append("- `canonical_company` ≥95%")
    lines.append("- `canonical_seniority` ≥85%")
    lines.append("- `canonical_location` ≥90%")
    lines.append("- `team_or_department` ≥90% precision (recall intentionally low)")
    lines.append("- `top_skills` Jaccard ≥0.6")
    lines.append("- `role_summary` \"embedding-suitable\" ≥80%")
    lines.append("")
    lines.append(
        "Below threshold → tune `prompts/canonical_extraction_v1.txt`, "
        "re-run failing samples, iterate (max 3 prompt-fix attempts per Gate 5)."
    )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate extract_canonical against all C19-passed postings."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_DEFAULT_DB_PATH,
        help=f"Path to SQLite DB (default: {_DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=_DEFAULT_REPORT_PATH,
        dest="report_out",
        help=f"Output path for Markdown report (default: {_DEFAULT_REPORT_PATH})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Extract only the first N passing postings (for dev iteration)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print which postings WOULD be extracted without spending tokens",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    db_path: Path = args.db
    if not db_path.exists():
        print(f"ERROR: DB not found at {db_path}")
        raise SystemExit(1)

    results, stats = run_validation(db_path, limit=args.limit, dry_run=args.dry_run)

    if args.dry_run:
        return

    report = generate_report(results, stats, db_path)

    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(report, encoding="utf-8")

    # Print summary to stdout
    print(f"Validation complete.")
    print(f"  Postings analyzed:      {stats.analyzed}")
    print(f"  Successful extractions: {stats.success}")
    print(f"  Parse failures:         {len(stats.failures)}")
    print(f"  Cache hits:             {stats.cache_hits}")
    print(f"  New API calls:          {stats.new_api_calls}")
    print(f"  Cost (this run):        ${stats.run_cost_usd:.6f}")
    print(f"  Total cost to date:     ${_total_ledger_cost(db_path):.6f}")
    print(f"  Report written to:      {args.report_out}")

    if stats.failures:
        print("\nFAILURES:")
        for pid, reason in stats.failures:
            print(f"  Posting ID {pid}: {reason[:120]}")


if __name__ == "__main__":
    _main()
