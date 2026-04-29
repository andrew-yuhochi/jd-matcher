"""
C22 — State Manager extension (canonical-id-keyed dedup state).

Read-side companion to C7 (state/manager.py). C7 remains the only write API.
This module resolves canonical-level state from posting-level applied/dismissed rows,
using JOIN-based state inheritance through posting_canonical_links.

The apply-one-suppress-all invariant is implicit via SQL JOIN — no write-time
propagation needed. Applying or dismissing ANY linked posting suppresses the
canonical from Main on next select_main() call.

Public API:
  is_canonical_applied(canonical_id, user_id, db_path) -> bool
  is_canonical_dismissed(canonical_id, user_id, db_path) -> bool
  select_main(user_id, db_path) -> list[CanonicalCard]
  get_canonical_state(canonical_id, user_id, db_path) -> CanonicalStateView
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class CanonicalStateView(BaseModel):
    canonical_id: int
    is_applied: bool
    is_dismissed: bool
    applied_via_posting_id: Optional[int]
    dismissed_via_posting_id: Optional[int]
    suppress_from_main: bool


class CanonicalCard(BaseModel):
    canonical_id: int
    canonical_title: Optional[str]
    canonical_company: Optional[str]
    canonical_seniority: Optional[str]
    canonical_location: Optional[str]
    team_or_department: Optional[str]
    top_skills: Optional[list[str]]
    role_summary: Optional[str]
    first_seen: Optional[str]
    last_seen: Optional[str]
    sources_summary: list[str]
    merge_kind_history: list[str]


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


def _open_conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or _DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ---------------------------------------------------------------------------
# Public API — read-only
# ---------------------------------------------------------------------------


def is_canonical_applied(
    canonical_id: int,
    user_id: str = "default",
    db_path: Path | None = None,
) -> bool:
    """Return True if ANY posting linked to canonical_id is in applied for user_id."""
    conn = _open_conn(db_path)
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM posting_canonical_links pcl
            JOIN applied a ON a.posting_id = pcl.posting_id
            WHERE pcl.canonical_id = ?
              AND a.user_id = ?
            LIMIT 1
            """,
            (canonical_id, user_id),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def is_canonical_dismissed(
    canonical_id: int,
    user_id: str = "default",
    db_path: Path | None = None,
) -> bool:
    """Return True if ANY posting linked to canonical_id is in dismissed for user_id."""
    conn = _open_conn(db_path)
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM posting_canonical_links pcl
            JOIN dismissed d ON d.posting_id = pcl.posting_id
            WHERE pcl.canonical_id = ?
              AND d.user_id = ?
            LIMIT 1
            """,
            (canonical_id, user_id),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def select_main(
    user_id: str = "default",
    db_path: Path | None = None,
) -> list[CanonicalCard]:
    """Return canonical cards not applied AND not dismissed for user_id.

    Uses NOT EXISTS subqueries so that applying or dismissing ANY linked posting
    suppresses the whole canonical — the apply-one-suppress-all invariant.

    Sources and merge_kind_history are aggregated from posting_canonical_links
    joined to posting_sources (falling back to source column if posting_sources
    has no row for a given posting).
    """
    conn = _open_conn(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                cp.canonical_id,
                cp.canonical_title,
                cp.canonical_company,
                cp.canonical_seniority,
                cp.canonical_location,
                cp.team_or_department,
                cp.top_skills,
                cp.role_summary,
                cp.first_seen,
                cp.last_seen
            FROM canonical_postings cp
            WHERE NOT EXISTS (
                SELECT 1
                FROM posting_canonical_links pcl
                JOIN applied a ON a.posting_id = pcl.posting_id
                WHERE pcl.canonical_id = cp.canonical_id
                  AND a.user_id = ?
            )
            AND NOT EXISTS (
                SELECT 1
                FROM posting_canonical_links pcl
                JOIN dismissed d ON d.posting_id = pcl.posting_id
                WHERE pcl.canonical_id = cp.canonical_id
                  AND d.user_id = ?
            )
            ORDER BY cp.first_seen DESC
            """,
            (user_id, user_id),
        ).fetchall()
    finally:
        conn.close()

    cards: list[CanonicalCard] = []
    for row in rows:
        (
            canonical_id, canonical_title, canonical_company,
            canonical_seniority, canonical_location, team_or_department,
            top_skills_raw, role_summary, first_seen, last_seen,
        ) = row

        top_skills = _parse_json_list(top_skills_raw)
        sources_summary, merge_kind_history = _aggregate_link_info(canonical_id, db_path)

        cards.append(CanonicalCard(
            canonical_id=canonical_id,
            canonical_title=canonical_title,
            canonical_company=canonical_company,
            canonical_seniority=canonical_seniority,
            canonical_location=canonical_location,
            team_or_department=team_or_department,
            top_skills=top_skills,
            role_summary=role_summary,
            first_seen=first_seen,
            last_seen=last_seen,
            sources_summary=sources_summary,
            merge_kind_history=merge_kind_history,
        ))

    return cards


def get_canonical_state(
    canonical_id: int,
    user_id: str = "default",
    db_path: Path | None = None,
) -> CanonicalStateView:
    """Return full canonical-level state view including which posting drove the state."""
    conn = _open_conn(db_path)
    try:
        applied_row = conn.execute(
            """
            SELECT pcl.posting_id
            FROM posting_canonical_links pcl
            JOIN applied a ON a.posting_id = pcl.posting_id
            WHERE pcl.canonical_id = ?
              AND a.user_id = ?
            LIMIT 1
            """,
            (canonical_id, user_id),
        ).fetchone()

        dismissed_row = conn.execute(
            """
            SELECT pcl.posting_id
            FROM posting_canonical_links pcl
            JOIN dismissed d ON d.posting_id = pcl.posting_id
            WHERE pcl.canonical_id = ?
              AND d.user_id = ?
            LIMIT 1
            """,
            (canonical_id, user_id),
        ).fetchone()
    finally:
        conn.close()

    is_applied = applied_row is not None
    is_dismissed = dismissed_row is not None

    return CanonicalStateView(
        canonical_id=canonical_id,
        is_applied=is_applied,
        is_dismissed=is_dismissed,
        applied_via_posting_id=applied_row[0] if applied_row else None,
        dismissed_via_posting_id=dismissed_row[0] if dismissed_row else None,
        suppress_from_main=is_applied or is_dismissed,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _aggregate_link_info(
    canonical_id: int,
    db_path: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Return (sources_summary, merge_kind_history) for a canonical.

    sources_summary: distinct source labels from posting_sources (or 'unknown' fallback).
    merge_kind_history: distinct merge_kind values from posting_canonical_links.
    """
    conn = _open_conn(db_path)
    try:
        link_rows = conn.execute(
            """
            SELECT pcl.posting_id, pcl.merge_kind,
                   COALESCE(ps.source, 'unknown') AS source_label
            FROM posting_canonical_links pcl
            LEFT JOIN posting_sources ps ON ps.posting_id = pcl.posting_id
            WHERE pcl.canonical_id = ?
            """,
            (canonical_id,),
        ).fetchall()
    finally:
        conn.close()

    sources: list[str] = []
    merge_kinds: list[str] = []
    seen_sources: set[str] = set()
    seen_kinds: set[str] = set()

    for _pid, merge_kind, source_label in link_rows:
        if source_label not in seen_sources:
            sources.append(source_label)
            seen_sources.add(source_label)
        if merge_kind and merge_kind not in seen_kinds:
            merge_kinds.append(merge_kind)
            seen_kinds.add(merge_kind)

    return sources, merge_kinds


def _parse_json_list(raw: Optional[str]) -> Optional[list[str]]:
    """Parse a JSON-encoded string list, returning None if raw is None or invalid."""
    if raw is None:
        return None
    import json
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else None
    except (json.JSONDecodeError, TypeError):
        return None
