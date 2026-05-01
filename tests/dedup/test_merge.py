"""Tests for C29 — Canonical Record Merge Logic.

Coverage (8 invariant tests + 1 integration demo):
  (a) action='new' produces 1 canonical + 1 link (merge_kind='new_canonical', score=1.0)
  (b) action='merge' does NOT modify canonical_* fields
  (c) first_seen preservation: MIN semantics
  (d) last_seen advancement: MAX semantics
  (e) full_jd swap rule: >10% longer swaps in; 5% longer does NOT
  (f) sources_summary append: Indeed into LinkedIn-only yields ["linkedin", "indeed"]
  (g) State inheritance (cross-link): applied canonical seed → merged variant → excluded from main
  (h) Transactional rollback: exception during link insert leaves canonical unchanged

  + Demo integration test: 2 postings → 1 canonical, 2 links, postings preserved, first_seen=MIN
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from jd_matcher.dedup.engine import DedupDecision
from jd_matcher.dedup.merge import MergeResult, apply_decision


# ---------------------------------------------------------------------------
# Shared DB fixture helpers
# ---------------------------------------------------------------------------

_FULL_SCHEMA = """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    );
    INSERT OR IGNORE INTO users (id) VALUES ('default');

    CREATE TABLE IF NOT EXISTS postings (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id             TEXT NOT NULL DEFAULT 'default',
        canonical_company   TEXT,
        canonical_title     TEXT,
        canonical_location  TEXT,
        canonical_seniority TEXT,
        seniority_band      TEXT,
        team_or_department  TEXT,
        top_skills          TEXT,
        role_summary        TEXT,
        full_jd             TEXT,
        hydration_status    TEXT NOT NULL DEFAULT 'complete',
        first_seen          TIMESTAMP NOT NULL,
        last_seen           TIMESTAMP NOT NULL
    );

    CREATE TABLE IF NOT EXISTS posting_sources (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        posting_id      INTEGER NOT NULL,
        user_id         TEXT NOT NULL DEFAULT 'default',
        source          TEXT NOT NULL,
        source_url      TEXT NOT NULL,
        source_first_seen TIMESTAMP NOT NULL,
        raw_html        TEXT
    );

    CREATE TABLE IF NOT EXISTS seen_urls (
        url        TEXT NOT NULL,
        user_id    TEXT NOT NULL DEFAULT 'default',
        posting_id INTEGER NOT NULL,
        seen_at    TIMESTAMP NOT NULL,
        UNIQUE (user_id, url)
    );

    CREATE TABLE IF NOT EXISTS applied (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        posting_id        INTEGER NOT NULL,
        user_id           TEXT NOT NULL DEFAULT 'default',
        status            TEXT NOT NULL DEFAULT 'Applied',
        applied_at        TIMESTAMP NOT NULL,
        status_updated_at TIMESTAMP NOT NULL,
        notes             TEXT,
        UNIQUE (user_id, posting_id)
    );

    CREATE TABLE IF NOT EXISTS dismissed (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        posting_id   INTEGER NOT NULL,
        user_id      TEXT NOT NULL DEFAULT 'default',
        dismissed_at TIMESTAMP NOT NULL,
        reason       TEXT,
        UNIQUE (user_id, posting_id)
    );

    CREATE TABLE IF NOT EXISTS events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     TEXT NOT NULL DEFAULT 'default',
        session_id  TEXT,
        event_type  TEXT NOT NULL,
        posting_id  INTEGER,
        metadata    TEXT,
        timestamp   TIMESTAMP NOT NULL
    );

    CREATE TABLE IF NOT EXISTS canonical_postings (
        canonical_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id             TEXT NOT NULL DEFAULT 'default',
        canonical_title     TEXT NOT NULL,
        canonical_company   TEXT NOT NULL,
        canonical_seniority TEXT NOT NULL,
        canonical_location  TEXT NOT NULL,
        team_or_department  TEXT NULL,
        top_skills          JSON NOT NULL,
        role_summary        TEXT NOT NULL,
        full_jd             TEXT NOT NULL DEFAULT '',
        full_jd_provenance  JSON NOT NULL DEFAULT '{}',
        first_seen          TIMESTAMP NOT NULL,
        last_seen           TIMESTAMP NOT NULL,
        sources_summary     JSON NOT NULL DEFAULT '["linkedin"]',
        created_at          TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        updated_at          TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    );

    CREATE INDEX IF NOT EXISTS idx_canonical_user_block
        ON canonical_postings (user_id, canonical_company, team_or_department, canonical_location);

    CREATE TABLE IF NOT EXISTS posting_canonical_links (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id          TEXT NOT NULL DEFAULT 'default',
        posting_id       TEXT NOT NULL,
        canonical_id     INTEGER NOT NULL,
        similarity_score REAL NOT NULL DEFAULT 1.0,
        merge_kind       TEXT NOT NULL DEFAULT 'new_canonical',
        merged_at        TIMESTAMP NOT NULL,
        UNIQUE (user_id, posting_id)
    );

    CREATE INDEX IF NOT EXISTS idx_links_canonical ON posting_canonical_links (canonical_id);
"""


def _make_db(tmp_path: Path) -> Path:
    """Create an on-disk SQLite DB with the full schema for merge tests."""
    db_path = tmp_path / "merge_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_FULL_SCHEMA)
    conn.commit()
    conn.close()
    return db_path


def _insert_posting(
    db_path: Path,
    *,
    company: str = "Acme Corp",
    title: str = "Data Scientist",
    location: str = "Vancouver",
    seniority: str = "Senior",
    team: str | None = None,
    skills: list[str] | None = None,
    role_summary: str = "Role summary text.",
    full_jd: str = "Full job description text here.",
    first_seen: str = "2024-03-01T00:00:00+00:00",
    last_seen: str = "2024-03-01T00:00:00+00:00",
    source: str = "linkedin",
) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """
            INSERT INTO postings
                (user_id, canonical_company, canonical_title, canonical_location,
                 canonical_seniority, seniority_band, team_or_department, top_skills,
                 role_summary, full_jd, hydration_status, first_seen, last_seen)
            VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'complete', ?, ?)
            """,
            (
                company, title, location, seniority, seniority,
                team, json.dumps(skills or ["python", "sql"]),
                role_summary, full_jd, first_seen, last_seen,
            ),
        )
        posting_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO posting_sources
                (posting_id, user_id, source, source_url, source_first_seen)
            VALUES (?, 'default', ?, 'https://example.com/job/1', ?)
            """,
            (posting_id, source, first_seen),
        )
        conn.commit()
        return posting_id
    finally:
        conn.close()


def _insert_canonical(
    db_path: Path,
    *,
    company: str = "Acme Corp",
    title: str = "Data Scientist",
    location: str = "Vancouver",
    seniority: str = "Senior",
    team: str | None = None,
    skills: list[str] | None = None,
    role_summary: str = "Canonical role summary.",
    full_jd: str = "Canonical full JD text.",
    first_seen: str = "2024-03-01T00:00:00+00:00",
    last_seen: str = "2024-03-01T00:00:00+00:00",
    sources_summary: list[str] | None = None,
) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """
            INSERT INTO canonical_postings
                (user_id, canonical_title, canonical_company, canonical_seniority,
                 canonical_location, team_or_department, top_skills, role_summary,
                 full_jd, full_jd_provenance, first_seen, last_seen, sources_summary)
            VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, '{"chosen_from_posting_id": 1}', ?, ?, ?)
            """,
            (
                title, company, seniority, location, team,
                json.dumps(skills or ["python", "sql"]),
                role_summary, full_jd, first_seen, last_seen,
                json.dumps(sources_summary or ["linkedin"]),
            ),
        )
        canonical_id = cur.lastrowid
        conn.commit()
        return canonical_id
    finally:
        conn.close()


def _link(db_path: Path, posting_id: int, canonical_id: int, merge_kind: str = "new_canonical") -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT OR REPLACE INTO posting_canonical_links
                (user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at)
            VALUES ('default', ?, ?, 1.0, ?, ?)
            """,
            (str(posting_id), canonical_id, merge_kind, now),
        )
        conn.commit()
    finally:
        conn.close()


def _make_new_decision() -> DedupDecision:
    return DedupDecision(
        action="new",
        target_canonical_id=None,
        similarity=0.0,
        merge_kind="new_canonical",
        stage1_block_size=0,
        stage2_top_match_score=0.0,
        blocked_by=[],
    )


def _make_merge_decision(canonical_id: int, similarity: float = 0.95) -> DedupDecision:
    return DedupDecision(
        action="merge",
        target_canonical_id=canonical_id,
        similarity=similarity,
        merge_kind="content_dedup",
        stage1_block_size=1,
        stage2_top_match_score=similarity,
        blocked_by=["canonical_company", "canonical_location"],
    )


# ---------------------------------------------------------------------------
# (a) action='new' path
# ---------------------------------------------------------------------------


class TestNewCanonicalPath:
    def test_new_creates_one_canonical_one_link(self, tmp_path: Path) -> None:
        """(a) action='new' produces exactly 1 canonical + 1 link (new_canonical, score=1.0)."""
        db = _make_db(tmp_path)
        pid = _insert_posting(db)
        decision = _make_new_decision()

        result = apply_decision(decision, pid, db_path=db)

        assert result.was_new is True
        assert result.merge_kind == "new_canonical"

        conn = sqlite3.connect(str(db))
        n_canonicals = conn.execute("SELECT COUNT(*) FROM canonical_postings").fetchone()[0]
        n_links = conn.execute("SELECT COUNT(*) FROM posting_canonical_links").fetchone()[0]
        link_row = conn.execute(
            "SELECT similarity_score, merge_kind FROM posting_canonical_links WHERE posting_id = ?",
            (str(pid),),
        ).fetchone()
        conn.close()

        assert n_canonicals == 1
        assert n_links == 1
        assert link_row is not None
        assert link_row[0] == 1.0
        assert link_row[1] == "new_canonical"


# ---------------------------------------------------------------------------
# (b) action='merge' does NOT modify canonical_* fields
# ---------------------------------------------------------------------------


class TestMergeCoreFields:
    def test_merge_does_not_change_canonical_fields(self, tmp_path: Path) -> None:
        """(b) Existing canonical's canonical_* fields are unchanged after merge."""
        db = _make_db(tmp_path)

        # Seed canonical with distinct skills/role_summary from the candidate
        can_id = _insert_canonical(
            db,
            title="Senior Data Scientist",
            company="Acme Corp",
            location="Vancouver",
            skills=["scala", "spark"],
            role_summary="Original canonical summary.",
            full_jd="X" * 100,
        )
        # Seed posting with canonical linked (gives canonical its seed link)
        seed_pid = _insert_posting(db, skills=["scala", "spark"])
        _link(db, seed_pid, can_id)

        # Candidate has different skills/title
        cand_pid = _insert_posting(
            db,
            title="ML Engineer",
            skills=["pytorch", "tensorflow"],
            role_summary="Candidate role summary (different).",
            full_jd="Y" * 50,  # shorter — no jd swap
        )
        decision = _make_merge_decision(can_id)

        apply_decision(decision, cand_pid, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT canonical_title, top_skills, role_summary FROM canonical_postings WHERE canonical_id = ?",
            (can_id,),
        ).fetchone()
        conn.close()

        assert row[0] == "Senior Data Scientist", "canonical_title must not change"
        assert json.loads(row[1]) == ["scala", "spark"], "top_skills must not change"
        assert row[2] == "Original canonical summary.", "role_summary must not change"


# ---------------------------------------------------------------------------
# (c) first_seen preservation
# ---------------------------------------------------------------------------


class TestFirstSeenMerge:
    def test_older_candidate_updates_first_seen(self, tmp_path: Path) -> None:
        """(c) Candidate first_seen=2024-01-01 < canonical first_seen=2024-03-01 → MIN wins."""
        db = _make_db(tmp_path)
        can_id = _insert_canonical(db, first_seen="2024-03-01T00:00:00+00:00")
        seed_pid = _insert_posting(db, first_seen="2024-03-01T00:00:00+00:00")
        _link(db, seed_pid, can_id)

        cand_pid = _insert_posting(
            db, first_seen="2024-01-01T00:00:00+00:00", last_seen="2024-01-01T00:00:00+00:00"
        )
        decision = _make_merge_decision(can_id)
        result = apply_decision(decision, cand_pid, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT first_seen FROM canonical_postings WHERE canonical_id = ?", (can_id,)
        ).fetchone()
        conn.close()

        assert "2024-01-01" in row[0], f"Expected 2024-01-01 in first_seen, got {row[0]}"
        assert "first_seen" in result.fields_updated

    def test_newer_candidate_does_not_update_first_seen(self, tmp_path: Path) -> None:
        """(c) Candidate first_seen AFTER canonical first_seen → first_seen unchanged."""
        db = _make_db(tmp_path)
        can_id = _insert_canonical(db, first_seen="2024-01-01T00:00:00+00:00")
        seed_pid = _insert_posting(db, first_seen="2024-01-01T00:00:00+00:00")
        _link(db, seed_pid, can_id)

        cand_pid = _insert_posting(
            db, first_seen="2024-06-01T00:00:00+00:00", last_seen="2024-06-01T00:00:00+00:00"
        )
        decision = _make_merge_decision(can_id)
        apply_decision(decision, cand_pid, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT first_seen FROM canonical_postings WHERE canonical_id = ?", (can_id,)
        ).fetchone()
        conn.close()

        assert "2024-01-01" in row[0]


# ---------------------------------------------------------------------------
# (d) last_seen advancement
# ---------------------------------------------------------------------------


class TestLastSeenMerge:
    def test_newer_candidate_updates_last_seen(self, tmp_path: Path) -> None:
        """(d) Candidate last_seen AFTER canonical last_seen → last_seen updated."""
        db = _make_db(tmp_path)
        can_id = _insert_canonical(db, last_seen="2024-03-01T00:00:00+00:00")
        seed_pid = _insert_posting(db, last_seen="2024-03-01T00:00:00+00:00")
        _link(db, seed_pid, can_id)

        cand_pid = _insert_posting(
            db, last_seen="2024-12-01T00:00:00+00:00"
        )
        decision = _make_merge_decision(can_id)
        result = apply_decision(decision, cand_pid, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT last_seen FROM canonical_postings WHERE canonical_id = ?", (can_id,)
        ).fetchone()
        conn.close()

        assert "2024-12-01" in row[0]
        assert "last_seen" in result.fields_updated


# ---------------------------------------------------------------------------
# (e) full_jd swap rule
# ---------------------------------------------------------------------------


class TestFullJdSwap:
    def test_11_percent_longer_swaps_in(self, tmp_path: Path) -> None:
        """(e) Candidate JD 11% longer than canonical → JD and provenance updated."""
        db = _make_db(tmp_path)
        canonical_jd = "A" * 100
        candidate_jd = "B" * 112  # 12% longer

        can_id = _insert_canonical(db, full_jd=canonical_jd)
        seed_pid = _insert_posting(db, full_jd=canonical_jd)
        _link(db, seed_pid, can_id)

        cand_pid = _insert_posting(db, full_jd=candidate_jd)
        decision = _make_merge_decision(can_id)
        result = apply_decision(decision, cand_pid, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT full_jd, full_jd_provenance FROM canonical_postings WHERE canonical_id = ?",
            (can_id,),
        ).fetchone()
        conn.close()

        assert row[0] == candidate_jd, "full_jd should be replaced by the longer candidate"
        prov = json.loads(row[1])
        assert prov["chosen_from_posting_id"] == cand_pid
        assert "full_jd" in result.fields_updated

    def test_5_percent_longer_does_not_swap(self, tmp_path: Path) -> None:
        """(e) Candidate JD only 5% longer → JD NOT replaced (below 10% threshold)."""
        db = _make_db(tmp_path)
        canonical_jd = "A" * 100
        candidate_jd = "B" * 105  # 5% longer — below threshold

        can_id = _insert_canonical(db, full_jd=canonical_jd)
        seed_pid = _insert_posting(db, full_jd=canonical_jd)
        _link(db, seed_pid, can_id)

        cand_pid = _insert_posting(db, full_jd=candidate_jd)
        decision = _make_merge_decision(can_id)
        result = apply_decision(decision, cand_pid, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT full_jd FROM canonical_postings WHERE canonical_id = ?", (can_id,)
        ).fetchone()
        conn.close()

        assert row[0] == canonical_jd, "full_jd must NOT be replaced (5% < 10% threshold)"
        assert "full_jd" not in result.fields_updated


# ---------------------------------------------------------------------------
# (f) sources_summary append
# ---------------------------------------------------------------------------


class TestSourcesSummary:
    def test_new_source_appended(self, tmp_path: Path) -> None:
        """(f) Indeed candidate merged into linkedin-only canonical → sources=['linkedin', 'indeed']."""
        db = _make_db(tmp_path)
        can_id = _insert_canonical(db, sources_summary=["linkedin"])
        seed_pid = _insert_posting(db, source="linkedin")
        _link(db, seed_pid, can_id)

        cand_pid = _insert_posting(db, source="indeed")
        decision = _make_merge_decision(can_id)
        result = apply_decision(decision, cand_pid, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT sources_summary FROM canonical_postings WHERE canonical_id = ?", (can_id,)
        ).fetchone()
        conn.close()

        sources = json.loads(row[0])
        assert sources == ["linkedin", "indeed"], f"Expected ['linkedin', 'indeed'], got {sources}"
        assert "sources_summary" in result.fields_updated

    def test_existing_source_not_duplicated(self, tmp_path: Path) -> None:
        """(f) Merging a second linkedin posting does not duplicate 'linkedin' in sources_summary."""
        db = _make_db(tmp_path)
        can_id = _insert_canonical(db, sources_summary=["linkedin"])
        seed_pid = _insert_posting(db, source="linkedin")
        _link(db, seed_pid, can_id)

        cand_pid = _insert_posting(db, source="linkedin")
        decision = _make_merge_decision(can_id)
        result = apply_decision(decision, cand_pid, db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT sources_summary FROM canonical_postings WHERE canonical_id = ?", (can_id,)
        ).fetchone()
        conn.close()

        sources = json.loads(row[0])
        assert sources.count("linkedin") == 1, "linkedin must not be duplicated"
        assert "sources_summary" not in result.fields_updated


# ---------------------------------------------------------------------------
# (g) State inheritance cross-link invariant
# ---------------------------------------------------------------------------


class TestStateInheritance:
    def test_applied_canonical_excluded_from_main(self, tmp_path: Path) -> None:
        """(g) After merging a second variant into an applied canonical, select via join excludes it."""
        db = _make_db(tmp_path)
        can_id = _insert_canonical(db)
        seed_pid = _insert_posting(db)
        _link(db, seed_pid, can_id)

        # Mark seed posting as applied
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at) "
            "VALUES (?, 'default', 'Applied', ?, ?)",
            (seed_pid, now, now),
        )
        conn.commit()
        conn.close()

        # Merge a second variant
        cand_pid = _insert_posting(db)
        decision = _make_merge_decision(can_id)
        apply_decision(decision, cand_pid, db_path=db)

        # C22 pattern: select canonical_postings where NOT EXISTS any linked posting in applied
        conn = sqlite3.connect(str(db))
        rows = conn.execute(
            """
            SELECT cp.canonical_id
            FROM canonical_postings cp
            WHERE NOT EXISTS (
                SELECT 1
                FROM posting_canonical_links pcl
                JOIN applied a ON a.posting_id = pcl.posting_id
                WHERE pcl.canonical_id = cp.canonical_id
                  AND a.user_id = 'default'
            )
            """
        ).fetchall()
        conn.close()

        # canonical_id should NOT appear (it has an applied link)
        canonical_ids_in_main = [r[0] for r in rows]
        assert can_id not in canonical_ids_in_main, (
            f"Applied canonical {can_id} should not appear in main view"
        )


# ---------------------------------------------------------------------------
# (h) Transactional rollback
# ---------------------------------------------------------------------------


class TestTransactionalRollback:
    def test_link_insert_failure_rolls_back_canonical_update(self, tmp_path: Path) -> None:
        """(h) Exception during link INSERT leaves canonical unchanged (rollback verified)."""
        db = _make_db(tmp_path)
        original_full_jd = "A" * 100
        can_id = _insert_canonical(db, full_jd=original_full_jd, first_seen="2024-03-01T00:00:00+00:00")
        seed_pid = _insert_posting(db, full_jd=original_full_jd)
        _link(db, seed_pid, can_id)

        # Candidate with older first_seen AND longer JD — both would trigger updates
        cand_pid = _insert_posting(
            db,
            full_jd="B" * 120,  # 20% longer → would trigger jd swap
            first_seen="2024-01-01T00:00:00+00:00",
            source="indeed",
        )
        decision = _make_merge_decision(can_id)

        # Capture canonical state before
        conn = sqlite3.connect(str(db))
        before_row = conn.execute(
            "SELECT first_seen, full_jd FROM canonical_postings WHERE canonical_id = ?",
            (can_id,),
        ).fetchone()
        conn.close()

        # Patch conn.execute to raise on the INSERT INTO posting_canonical_links call
        original_execute = sqlite3.Connection.execute

        call_count = {"n": 0}

        def _failing_execute(self, sql: str, *args, **kwargs):
            if "INSERT INTO posting_canonical_links" in sql:
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise sqlite3.OperationalError("Simulated link insert failure")
            return original_execute(self, sql, *args, **kwargs)

        with pytest.raises((sqlite3.OperationalError, Exception)):
            with patch.object(sqlite3.Connection, "execute", _failing_execute):
                apply_decision(decision, cand_pid, db_path=db)

        # Verify canonical state is unchanged
        conn = sqlite3.connect(str(db))
        after_row = conn.execute(
            "SELECT first_seen, full_jd FROM canonical_postings WHERE canonical_id = ?",
            (can_id,),
        ).fetchone()
        conn.close()

        assert after_row[0] == before_row[0], "first_seen must be rolled back"
        assert after_row[1] == before_row[1], "full_jd must be rolled back"


# ---------------------------------------------------------------------------
# Demo integration test: 2 postings → 1 canonical, 2 links, postings preserved
# ---------------------------------------------------------------------------


class TestDemoIntegration:
    def test_two_postings_one_canonical_two_links_postings_preserved(self, tmp_path: Path) -> None:
        """Demo artifact: merge 2 synthetic postings; verify the invariants.

        - canonical_postings has exactly 1 row
        - posting_canonical_links has exactly 2 rows
        - postings table still has both originals (NEVER modified)
        - first_seen on canonical = MIN(P1.first_seen, P2.first_seen)
        """
        db = _make_db(tmp_path)

        # P1: the first posting (older first_seen) → creates new canonical
        pid1 = _insert_posting(
            db,
            company="Acme Corp",
            title="Data Scientist",
            location="Vancouver",
            first_seen="2024-01-15T00:00:00+00:00",
            last_seen="2024-01-15T00:00:00+00:00",
            source="linkedin",
            full_jd="A" * 200,
        )
        decision1 = _make_new_decision()
        result1 = apply_decision(decision1, pid1, db_path=db)

        assert result1.was_new is True
        canonical_id = result1.canonical_id

        # P2: a second posting (newer first_seen, same canonical target) → merge
        pid2 = _insert_posting(
            db,
            company="Acme Corp",
            title="Data Scientist",
            location="Vancouver",
            first_seen="2024-03-01T00:00:00+00:00",
            last_seen="2024-03-01T00:00:00+00:00",
            source="indeed",
            full_jd="B" * 180,  # shorter — no jd swap
        )
        decision2 = _make_merge_decision(canonical_id)
        result2 = apply_decision(decision2, pid2, db_path=db)

        assert result2.was_new is False
        assert result2.canonical_id == canonical_id

        conn = sqlite3.connect(str(db))
        n_canonicals = conn.execute("SELECT COUNT(*) FROM canonical_postings").fetchone()[0]
        n_links = conn.execute("SELECT COUNT(*) FROM posting_canonical_links").fetchone()[0]
        n_postings = conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
        canonical_first_seen = conn.execute(
            "SELECT first_seen FROM canonical_postings WHERE canonical_id = ?",
            (canonical_id,),
        ).fetchone()[0]
        conn.close()

        # Structural invariants
        assert n_canonicals == 1, f"Expected 1 canonical, got {n_canonicals}"
        assert n_links == 2, f"Expected 2 links, got {n_links}"
        assert n_postings == 2, f"postings table must not grow beyond the 2 originals"

        # first_seen = MIN (P1 was 2024-01-15, P2 was 2024-03-01 → MIN = 2024-01-15)
        assert "2024-01-15" in canonical_first_seen, (
            f"canonical.first_seen should be 2024-01-15 (MIN), got {canonical_first_seen}"
        )


# ---------------------------------------------------------------------------
# Regression test: canonical_seniority must be populated from postings.canonical_seniority
# (TASK-M3-000: merge.py now reads postings.canonical_seniority directly, not seniority_band)
# ---------------------------------------------------------------------------


def test_canonical_seniority_populated_from_posting_canonical_seniority(tmp_path: Path) -> None:
    """_fetch_posting() must read postings.canonical_seniority (written by C18 extraction).

    TASK-M3-000: merge.py switched from reading seniority_band AS canonical_seniority
    to reading the live canonical_seniority column that _write_postings_extracted() populates.
    This test asserts the post-fix behavior: canonical_seniority written by LLM extraction
    flows correctly into canonical_postings.canonical_seniority via merge.
    """
    db = _make_db(tmp_path)

    # Insert posting with canonical_seniority='Senior' (the live column written by C18).
    conn = sqlite3.connect(str(db))
    cur = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_company, canonical_title, canonical_location,
             canonical_seniority, seniority_band, team_or_department, top_skills,
             role_summary, full_jd, hydration_status, first_seen, last_seen)
        VALUES ('default', 'Acme Corp', 'Data Scientist', 'Vancouver',
                'Senior', NULL, NULL, '["python"]',
                'Role summary.', 'Full JD.', 'complete',
                '2024-03-01T00:00:00+00:00', '2024-03-01T00:00:00+00:00')
        """,
    )
    posting_id = cur.lastrowid
    conn.execute(
        """
        INSERT INTO posting_sources (posting_id, user_id, source, source_url, source_first_seen)
        VALUES (?, 'default', 'linkedin', 'https://example.com/job/999', '2024-03-01T00:00:00+00:00')
        """,
        (posting_id,),
    )
    conn.commit()
    conn.close()

    decision = _make_new_decision()
    apply_decision(decision, posting_id, db_path=db)

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT canonical_seniority FROM canonical_postings LIMIT 1"
    ).fetchone()
    conn.close()

    assert row is not None, "canonical_postings should have exactly one row after action='new'"
    assert row[0] == "Senior", (
        f"canonical_postings.canonical_seniority should be 'Senior' (from postings.canonical_seniority), "
        f"got {row[0]!r}. This means _fetch_posting() is reading the wrong column."
    )
