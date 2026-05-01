"""
Shared test helper functions for jd-matcher tests.

These are plain functions (not pytest fixtures) that can be imported by any
test module. The pytest fixtures in conftest.py wrap these functions.
"""

from __future__ import annotations

import sqlite3
from typing import Any

_TS = "2026-01-01T00:00:00+00:00"


def seed_posting(
    conn: sqlite3.Connection,
    *,
    title: str = "Senior Data Scientist",
    company: str = "Acme Corp",
    location: str = "Vancouver, BC",
    hydration_status: str = "complete",
    full_jd: str = "Full job description text.",
    role_summary: str = "A test role summary.",
    seniority: str | None = "Senior",
    first_seen: str = _TS,
    last_seen: str = _TS,
    **overrides: Any,
) -> int:
    """Insert a posting row with sensible defaults; return posting_id.

    Extra keyword arguments in ``overrides`` are accepted silently for call-site
    convenience when passing a superset of kwargs.
    """
    cur = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_title, canonical_company, canonical_location,
             hydration_status, full_jd, role_summary, seniority_band,
             canonical_seniority, first_seen, last_seen)
        VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (title, company, location, hydration_status, full_jd, role_summary,
         seniority, seniority, first_seen, last_seen),
    )
    conn.commit()
    return cur.lastrowid


def seed_canonical(
    conn: sqlite3.Connection,
    *,
    title: str = "Senior Data Scientist",
    company: str = "Acme Corp",
    location: str = "Vancouver, BC",
    seniority: str = "Senior",
    full_jd: str = "Full job description text.",
    role_summary: str = "A test role summary.",
    hydration_status: str = "complete",
    first_seen: str = _TS,
    last_seen: str = _TS,
    merge_kind: str = "new_canonical",
    similarity_score: float = 1.0,
    **overrides: Any,
) -> tuple[int, int]:
    """Insert posting + canonical_postings + link; return (posting_id, canonical_id).

    Caller must commit if autocommit is off on the connection; this helper
    calls conn.commit() after each INSERT to avoid leaving the transaction open.
    """
    posting_id = seed_posting(
        conn,
        title=title,
        company=company,
        location=location,
        hydration_status=hydration_status,
        full_jd=full_jd,
        role_summary=role_summary,
        seniority=seniority,
        first_seen=first_seen,
        last_seen=last_seen,
    )

    cur = conn.execute(
        """
        INSERT INTO canonical_postings
            (user_id, canonical_title, canonical_company, canonical_seniority,
             canonical_location, top_skills, role_summary, full_jd,
             full_jd_provenance, first_seen, last_seen, sources_summary)
        VALUES ('default', ?, ?, ?, ?, '[]', ?, ?, '{}', ?, ?, '["linkedin"]')
        """,
        (title, company, seniority, location, role_summary, full_jd,
         first_seen, last_seen),
    )
    canonical_id = cur.lastrowid

    conn.execute(
        """
        INSERT INTO posting_canonical_links
            (user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at)
        VALUES ('default', ?, ?, ?, ?, ?)
        """,
        (posting_id, canonical_id, similarity_score, merge_kind, last_seen),
    )
    conn.commit()
    return posting_id, canonical_id
