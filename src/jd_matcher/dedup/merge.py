"""C29 — Canonical Record Merge Logic.

Public API:
    apply_decision(decision, candidate_id, db_path=None) -> MergeResult

Receives a DedupDecision (possibly retagged by C30) and a candidate posting_id.
Either creates a new canonical_postings row or merges the candidate into the
existing canonical.  Writes posting_canonical_links in both cases.

DATA PRESERVATION INVARIANT: the postings table is APPEND-ONLY.  C29's writes
are confined to canonical_postings (INSERT or UPDATE) and posting_canonical_links
(INSERT).  merge_kind and similarity_score are recorded AT decision time —
never overwritten on later runs — so future threshold re-tuning is supported.

All writes execute in a single transaction.  An exception during
posting_canonical_links INSERT rolls back any canonical_postings changes.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from jd_matcher.dedup.engine import DedupDecision

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class MergeResult(BaseModel):
    """Result of applying a DedupDecision via C29."""

    canonical_id: int
    was_new: bool
    fields_updated: list[str]
    merge_kind: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_posting(posting_id: int, conn: sqlite3.Connection) -> dict[str, Any]:
    """Return posting row as a dict; raises ValueError if not found."""
    row = conn.execute(
        """
        SELECT id, user_id, canonical_title, canonical_company, canonical_seniority,
               canonical_location, team_or_department, top_skills, role_summary,
               full_jd, first_seen, last_seen,
               COALESCE(source, 'linkedin') AS source
        FROM postings
        LEFT JOIN (
            SELECT posting_id AS ps_pid, source
            FROM posting_sources
            WHERE posting_id = ?
            LIMIT 1
        ) ON ps_pid = id
        WHERE id = ?
        """,
        (posting_id, posting_id),
    ).fetchone()
    if row is None:
        raise ValueError(f"Posting {posting_id} not found")
    (
        pid, user_id, title, company, seniority, location,
        team, raw_skills, role_summary, full_jd, first_seen, last_seen, source,
    ) = row
    try:
        skills: list[str] = json.loads(raw_skills) if raw_skills else []
    except (json.JSONDecodeError, TypeError):
        skills = []
    return {
        "id": pid,
        "user_id": user_id or "default",
        "canonical_title": title or "",
        "canonical_company": company or "",
        "canonical_seniority": seniority or "",
        "canonical_location": location or "",
        "team_or_department": team,
        "top_skills": skills,
        "role_summary": role_summary or "",
        "full_jd": full_jd or "",
        "first_seen": first_seen,
        "last_seen": last_seen,
        "source": source or "linkedin",
    }


def _fetch_posting_source(posting_id: int, conn: sqlite3.Connection) -> str:
    """Return the source label for a posting, defaulting to 'linkedin'."""
    row = conn.execute(
        "SELECT source FROM posting_sources WHERE posting_id = ? LIMIT 1",
        (posting_id,),
    ).fetchone()
    if row:
        return row[0]
    # Fallback: infer from seen_urls
    row = conn.execute(
        "SELECT url FROM seen_urls WHERE posting_id = ? LIMIT 1",
        (posting_id,),
    ).fetchone()
    if row and row[0]:
        url = row[0]
        if "indeed" in url:
            return "indeed"
        if "jobbank" in url:
            return "jobbank"
    return "linkedin"


def _insert_new_canonical(
    posting: dict[str, Any],
    conn: sqlite3.Connection,
    now: str,
) -> int:
    """INSERT a new row in canonical_postings from the candidate posting's fields.

    Returns the new canonical_id.
    """
    provenance = json.dumps(
        {"chosen_from_posting_id": posting["id"], "source": posting["source"]}
    )
    sources_summary = json.dumps([posting["source"]])

    cur = conn.execute(
        """
        INSERT INTO canonical_postings (
            user_id, canonical_title, canonical_company, canonical_seniority,
            canonical_location, team_or_department, top_skills, role_summary,
            full_jd, full_jd_provenance, first_seen, last_seen,
            sources_summary, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            posting["user_id"],
            posting["canonical_title"],
            posting["canonical_company"],
            posting["canonical_seniority"],
            posting["canonical_location"],
            posting["team_or_department"],
            json.dumps(posting["top_skills"]),
            posting["role_summary"],
            posting["full_jd"],
            provenance,
            posting["first_seen"],
            posting["last_seen"],
            sources_summary,
            now,
            now,
        ),
    )
    return cur.lastrowid


def _compute_field_updates(
    posting: dict[str, Any],
    canonical: dict[str, Any],
    now: str,
) -> tuple[list[str], dict[str, Any]]:
    """Compute which fields on the canonical row should be updated on merge.

    Returns (fields_updated, update_values_dict).

    Merge rules (TDD §C29):
    - canonical_* / top_skills / role_summary / team_or_department: UNCHANGED
    - first_seen: MIN(canonical, candidate)
    - last_seen: MAX(canonical, candidate)
    - full_jd: replace if candidate > canonical * 1.10
    - sources_summary: append candidate.source if not already present
    - updated_at: always set to now
    """
    updates: dict[str, Any] = {"updated_at": now}
    fields_updated: list[str] = []

    # first_seen: take MIN
    cand_first = posting["first_seen"]
    can_first = canonical["first_seen"]
    if cand_first and can_first and cand_first < can_first:
        updates["first_seen"] = cand_first
        fields_updated.append("first_seen")

    # last_seen: take MAX
    cand_last = posting["last_seen"]
    can_last = canonical["last_seen"]
    if cand_last and can_last and cand_last > can_last:
        updates["last_seen"] = cand_last
        fields_updated.append("last_seen")

    # full_jd: swap if candidate is >10% longer
    cand_jd = posting["full_jd"] or ""
    can_jd = canonical["full_jd"] or ""
    if len(cand_jd) > len(can_jd) * 1.10:
        updates["full_jd"] = cand_jd
        updates["full_jd_provenance"] = json.dumps(
            {"chosen_from_posting_id": posting["id"], "source": posting["source"]}
        )
        fields_updated.extend(["full_jd", "full_jd_provenance"])

    # sources_summary: append if new source
    existing_sources: list[str] = canonical["sources_summary"]
    if posting["source"] not in existing_sources:
        new_sources = existing_sources + [posting["source"]]
        updates["sources_summary"] = json.dumps(new_sources)
        fields_updated.append("sources_summary")

    return fields_updated, updates


def _apply_merge(
    canonical_id: int,
    posting: dict[str, Any],
    conn: sqlite3.Connection,
    now: str,
) -> list[str]:
    """Apply merge-path field updates to canonical_postings.

    Returns the list of field names that were changed.
    """
    row = conn.execute(
        """
        SELECT canonical_title, canonical_company, canonical_seniority,
               canonical_location, team_or_department, top_skills, role_summary,
               full_jd, full_jd_provenance, first_seen, last_seen, sources_summary
        FROM canonical_postings
        WHERE canonical_id = ?
        """,
        (canonical_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Canonical {canonical_id} not found")

    (
        c_title, c_company, c_seniority, c_location, c_team,
        raw_top_skills, c_role_summary, c_full_jd, c_prov,
        c_first_seen, c_last_seen, raw_sources,
    ) = row

    try:
        existing_sources: list[str] = json.loads(raw_sources) if raw_sources else []
    except (json.JSONDecodeError, TypeError):
        existing_sources = []

    canonical = {
        "first_seen": c_first_seen,
        "last_seen": c_last_seen,
        "full_jd": c_full_jd or "",
        "sources_summary": existing_sources,
    }

    fields_updated, updates = _compute_field_updates(posting, canonical, now)

    # Build the UPDATE SET clause from non-trivial updates (updated_at always set)
    set_parts = ["updated_at = ?"]
    params: list[Any] = [now]

    for field in fields_updated:
        if field == "first_seen":
            set_parts.append("first_seen = ?")
            params.append(updates["first_seen"])
        elif field == "last_seen":
            set_parts.append("last_seen = ?")
            params.append(updates["last_seen"])
        elif field == "full_jd":
            set_parts.append("full_jd = ?")
            params.append(updates["full_jd"])
        elif field == "full_jd_provenance":
            set_parts.append("full_jd_provenance = ?")
            params.append(updates["full_jd_provenance"])
        elif field == "sources_summary":
            set_parts.append("sources_summary = ?")
            params.append(updates["sources_summary"])

    params.append(canonical_id)
    conn.execute(
        f"UPDATE canonical_postings SET {', '.join(set_parts)} WHERE canonical_id = ?",
        params,
    )

    logger.info(
        "C29 merge: canonical_id=%d updated fields=%s",
        canonical_id,
        fields_updated,
    )
    return fields_updated


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_decision(
    decision: DedupDecision,
    candidate_id: int,
    db_path: Path | None = None,
) -> MergeResult:
    """Apply a DedupDecision (from C21, possibly retagged by C30) to the database.

    For action='new': INSERT canonical_postings + INSERT posting_canonical_links.
    For action='merge': UPDATE canonical_postings (merge rules) + INSERT link.

    The postings table is NEVER modified.
    All writes execute in a single transaction (SQLite `with conn:` auto-commit
    on success, auto-rollback on exception).

    Args:
        decision:      Output of C21's decide(), possibly retagged by C30.
        candidate_id:  The posting_id of the candidate to process.
        db_path:       Path to SQLite DB; defaults to ~/.jd-matcher/jd-matcher.db.

    Returns:
        MergeResult with canonical_id, was_new flag, updated fields, and merge_kind.
    """
    resolved_db = db_path or _DEFAULT_DB_PATH
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(resolved_db)
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        with conn:  # auto-commit on exit, auto-rollback on exception
            # Resolve source separately (outside the transaction is fine — read-only)
            source = _fetch_posting_source(candidate_id, conn)

            # Re-fetch inside the transaction so reads are consistent with writes
            posting = _fetch_posting(candidate_id, conn)
            posting["source"] = source  # override with resolved source

            if decision.action == "pending_gatekeeper":
                # Fail-CLOSED: gatekeeper hard-failed.  The posting stays as-is —
                # no canonical created, no link written.  Next pipeline run retries.
                logger.info(
                    "C29 pending_gatekeeper: posting_id=%d — deferred (no DB writes)",
                    candidate_id,
                )
                raise ValueError(
                    f"apply_decision called with action='pending_gatekeeper' for "
                    f"posting {candidate_id}. C29 must not be called for deferred "
                    f"decisions — the caller (pipeline.py) must check the action "
                    f"before invoking apply_decision."
                )

            if decision.action == "new":
                canonical_id = _insert_new_canonical(posting, conn, now)

                conn.execute(
                    """
                    INSERT INTO posting_canonical_links
                        (user_id, posting_id, canonical_id, similarity_score,
                         merge_kind, merged_at)
                    VALUES (?, ?, ?, 1.0, 'new_canonical', ?)
                    """,
                    (posting["user_id"], str(candidate_id), canonical_id, now),
                )

                logger.info(
                    "C29 new: posting_id=%d → canonical_id=%d (source=%s)",
                    candidate_id,
                    canonical_id,
                    source,
                )
                return MergeResult(
                    canonical_id=canonical_id,
                    was_new=True,
                    fields_updated=[],
                    merge_kind="new_canonical",
                )

            else:  # action == "merge"
                canonical_id = decision.target_canonical_id  # type: ignore[assignment]
                fields_updated = _apply_merge(canonical_id, posting, conn, now)

                conn.execute(
                    """
                    INSERT INTO posting_canonical_links
                        (user_id, posting_id, canonical_id, similarity_score,
                         merge_kind, merged_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        posting["user_id"],
                        str(candidate_id),
                        canonical_id,
                        decision.similarity,
                        decision.merge_kind,
                        now,
                    ),
                )

                logger.info(
                    "C29 merge: posting_id=%d → canonical_id=%d merge_kind=%s fields=%s",
                    candidate_id,
                    canonical_id,
                    decision.merge_kind,
                    fields_updated,
                )
                return MergeResult(
                    canonical_id=canonical_id,
                    was_new=False,
                    fields_updated=fields_updated,
                    merge_kind=decision.merge_kind,
                )

    finally:
        conn.close()
