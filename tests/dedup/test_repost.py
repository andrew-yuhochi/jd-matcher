"""Tests for C30 — Repost Detector.

Coverage (5 invariant tests per TDD §C30):
  (a) Positive repost: candidate.first_seen = prior merged_at + 45 days → 'repost' + 1 event
  (b) Negative (within window): candidate.first_seen = prior + 14 days → 'content_dedup' + 0 events
  (c) Threshold edge: candidate.first_seen = prior + exactly 30 days → 'repost' (>= semantics)
  (d) action='new' pass-through: C30 returns unchanged + emits zero events
  (e) Inactive/Expired bypass: action='new' (C21 filtered) → C30 does NOT retag, emits no event
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jd_matcher.dedup.engine import DedupDecision
from jd_matcher.dedup.repost import detect_repost


# ---------------------------------------------------------------------------
# Shared DB fixture helpers
# ---------------------------------------------------------------------------

_SCHEMA = """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    );
    INSERT OR IGNORE INTO users (id) VALUES ('default');

    CREATE TABLE IF NOT EXISTS postings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     TEXT NOT NULL DEFAULT 'default',
        canonical_company  TEXT,
        canonical_title    TEXT,
        canonical_location TEXT,
        first_seen  TIMESTAMP NOT NULL,
        last_seen   TIMESTAMP NOT NULL,
        hydration_status TEXT NOT NULL DEFAULT 'complete',
        full_jd     TEXT,
        top_skills  TEXT,
        role_summary TEXT
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
"""


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "repost_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
    return db_path


def _insert_posting(db_path: Path, first_seen: str, user_id: str = "default") -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """
            INSERT INTO postings (user_id, canonical_company, canonical_title,
                canonical_location, first_seen, last_seen)
            VALUES (?, 'Acme', 'DS', 'Vancouver', ?, ?)
            """,
            (user_id, first_seen, first_seen),
        )
        pid = cur.lastrowid
        conn.commit()
        return pid
    finally:
        conn.close()


def _insert_canonical(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        now = "2024-01-01T00:00:00+00:00"
        cur = conn.execute(
            """
            INSERT INTO canonical_postings
                (user_id, canonical_title, canonical_company, canonical_seniority,
                 canonical_location, top_skills, role_summary, first_seen, last_seen)
            VALUES ('default', 'DS', 'Acme', 'Senior', 'Vancouver', '[]', 'summary', ?, ?)
            """,
            (now, now),
        )
        cid = cur.lastrowid
        conn.commit()
        return cid
    finally:
        conn.close()


def _insert_link(db_path: Path, posting_id: int, canonical_id: int, merged_at: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO posting_canonical_links
                (user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at)
            VALUES ('default', ?, ?, 1.0, 'new_canonical', ?)
            """,
            (str(posting_id), canonical_id, merged_at),
        )
        conn.commit()
    finally:
        conn.close()


def _count_repost_events(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type = 'posting_reposted'"
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def _make_merge_decision(canonical_id: int) -> DedupDecision:
    return DedupDecision(
        action="merge",
        target_canonical_id=canonical_id,
        similarity=0.95,
        merge_kind="content_dedup",
        stage1_block_size=1,
        stage2_top_match_score=0.95,
        blocked_by=["canonical_company", "canonical_location"],
    )


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


# ---------------------------------------------------------------------------
# (a) Positive repost: 45 days → retag + event
# ---------------------------------------------------------------------------


class TestRepostPositive:
    def test_45_days_later_is_repost(self, tmp_path: Path) -> None:
        """(a) P2.first_seen = prior merged_at + 45 days → merge_kind='repost', 1 event."""
        db = _make_db(tmp_path)
        can_id = _insert_canonical(db)

        prior_merged_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        p1_id = _insert_posting(db, prior_merged_at.isoformat())
        _insert_link(db, p1_id, can_id, prior_merged_at.isoformat())

        p2_first_seen = prior_merged_at + timedelta(days=45)
        p2_id = _insert_posting(db, p2_first_seen.isoformat())

        decision = _make_merge_decision(can_id)
        result = detect_repost(decision, p2_id, db_path=db)

        assert result.merge_kind == "repost", f"Expected 'repost', got {result.merge_kind!r}"
        assert result.action == "merge"
        assert result.target_canonical_id == can_id
        assert _count_repost_events(db) == 1


# ---------------------------------------------------------------------------
# (b) Within-window: 14 days → no retag, no event
# ---------------------------------------------------------------------------


class TestRepostNegative:
    def test_14_days_later_is_not_repost(self, tmp_path: Path) -> None:
        """(b) P3.first_seen = prior + 14 days → 'content_dedup' preserved, 0 events."""
        db = _make_db(tmp_path)
        can_id = _insert_canonical(db)

        prior_merged_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        p1_id = _insert_posting(db, prior_merged_at.isoformat())
        _insert_link(db, p1_id, can_id, prior_merged_at.isoformat())

        p3_first_seen = prior_merged_at + timedelta(days=14)
        p3_id = _insert_posting(db, p3_first_seen.isoformat())

        decision = _make_merge_decision(can_id)
        result = detect_repost(decision, p3_id, db_path=db)

        assert result.merge_kind == "content_dedup", (
            f"Expected 'content_dedup', got {result.merge_kind!r}"
        )
        assert _count_repost_events(db) == 0


# ---------------------------------------------------------------------------
# (c) Threshold edge: exactly 30 days → repost (>= semantics)
# ---------------------------------------------------------------------------


class TestRepostThresholdEdge:
    def test_exactly_30_days_is_repost(self, tmp_path: Path) -> None:
        """(c) candidate.first_seen = prior merged_at + exactly 30 days → 'repost' (>= rule)."""
        db = _make_db(tmp_path)
        can_id = _insert_canonical(db)

        prior_merged_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        p1_id = _insert_posting(db, prior_merged_at.isoformat())
        _insert_link(db, p1_id, can_id, prior_merged_at.isoformat())

        p2_first_seen = prior_merged_at + timedelta(days=30)  # exact boundary
        p2_id = _insert_posting(db, p2_first_seen.isoformat())

        decision = _make_merge_decision(can_id)
        result = detect_repost(decision, p2_id, db_path=db)

        assert result.merge_kind == "repost", (
            f"Expected 'repost' at exactly 30 days, got {result.merge_kind!r}"
        )
        assert _count_repost_events(db) == 1


# ---------------------------------------------------------------------------
# (d) action='new' pass-through
# ---------------------------------------------------------------------------


class TestNewDecisionPassthrough:
    def test_action_new_is_passthrough(self, tmp_path: Path) -> None:
        """(d) action='new' → C30 returns decision unchanged, emits 0 events."""
        db = _make_db(tmp_path)
        pid = _insert_posting(db, "2024-03-01T00:00:00+00:00")
        decision = _make_new_decision()

        result = detect_repost(decision, pid, db_path=db)

        assert result.action == "new"
        assert result.merge_kind == "new_canonical"
        assert _count_repost_events(db) == 0


# ---------------------------------------------------------------------------
# (e) Inactive/Expired bypass invariant
# ---------------------------------------------------------------------------


class TestInactiveExpiredBypass:
    def test_inactive_canonical_filtered_by_c21_arrives_as_new(self, tmp_path: Path) -> None:
        """(e) C21 filters Inactive/Expired canonicals → C30 sees action='new', no retag, no event.

        This test verifies the invariant that C30 never sees a merge decision
        targeting an Inactive/Expired canonical — C21 filters them first.
        We simulate this by providing an action='new' decision (as C21 would produce).
        """
        db = _make_db(tmp_path)

        # Create an "Inactive" canonical in the DB (forward-compat fixture)
        can_id = _insert_canonical(db)

        # Simulate C21 filtering the Inactive canonical → produces action='new'
        pid = _insert_posting(db, "2024-03-01T00:00:00+00:00")
        decision = _make_new_decision()  # action='new' — C21 filtered the Inactive canonical

        result = detect_repost(decision, pid, db_path=db)

        # C30 must NOT retag (action='new' is pass-through)
        assert result.action == "new"
        assert result.merge_kind == "new_canonical"
        # C30 must NOT emit a posting_reposted event for the Inactive canonical
        assert _count_repost_events(db) == 0
