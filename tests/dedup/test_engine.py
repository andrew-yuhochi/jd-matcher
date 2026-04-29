"""Tests for C21 — Two-Stage Dedup Engine (BLOCK + FUSE).

Coverage:
  - Unit tests for helpers: jaccard, seniority_match, title_cosine
  - 5 FUSE math tests with known inputs/outputs (AC-3)
  - 4 user-scenario synthetic fixture tests (AC-6):
      (i)   Same company + different teams → BOTH shown
      (ii)  Same company + same team + different roles → BOTH shown
      (iii) Same company + same team + same role + cross-source → MERGE
      (iv)  Same company + same team + same role + different location → BOTH shown
  - 10 different-team synthetic pairs → ZERO false merges (AC-7, SC-7)
  - full_jd-fallback short-circuit test (design add-on)
  - Inactive/Expired bypass test (AC-5)
  - DedupDecision JSON serialization round-trip (AC-8)
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jd_matcher.dedup.engine import (
    DedupConfig,
    DedupDecision,
    _CanonicalCandidate,
    _PostingRow,
    _block_lookup,
    _compute_fuse_score,
    decide,
    jaccard,
    seniority_match,
    title_cosine,
)
from jd_matcher.llm.embed import cosine


# ---------------------------------------------------------------------------
# Fixtures — in-memory SQLite DB with minimal schema
# ---------------------------------------------------------------------------


def _make_test_db() -> sqlite3.Connection:
    """Create an in-memory SQLite DB with the minimal schema for C21 tests."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id         TEXT PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        );
        INSERT OR IGNORE INTO users (id) VALUES ('default');

        CREATE TABLE IF NOT EXISTS postings (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             TEXT NOT NULL DEFAULT 'default',
            canonical_company   TEXT,
            canonical_title     TEXT,
            canonical_location  TEXT,
            seniority_band      TEXT,
            team_or_department  TEXT,
            top_skills          TEXT,
            role_summary        TEXT,
            full_jd             TEXT,
            hydration_status    TEXT NOT NULL DEFAULT 'complete',
            first_seen          TIMESTAMP NOT NULL,
            last_seen           TIMESTAMP NOT NULL
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
            sources_summary     JSON NOT NULL DEFAULT '[]',
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

        CREATE TABLE IF NOT EXISTS posting_embeddings (
            posting_id      TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL DEFAULT 'default',
            text_source     TEXT NOT NULL,
            text_hash       TEXT NOT NULL,
            embedding       BLOB NOT NULL,
            embedding_dim   INTEGER NOT NULL,
            model_name      TEXT NOT NULL DEFAULT 'text-embedding-3-small',
            embedded_at     TIMESTAMP NOT NULL
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
    """)
    conn.commit()
    return conn


def _pack_vec(vec: list[float]) -> bytes:
    return np.array(vec, dtype=np.float32).tobytes()


def _insert_posting(
    conn: sqlite3.Connection,
    *,
    company: str,
    title: str,
    location: str,
    team: str | None = None,
    seniority: str | None = None,
    skills: list[str] | None = None,
    role_summary: str = "A sample role summary.",
    full_jd: str | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_company, canonical_title, canonical_location,
             team_or_department, seniority_band, top_skills, role_summary, full_jd,
             hydration_status, first_seen, last_seen)
        VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, 'complete', ?, ?)
        """,
        (
            company, title, location, team, seniority,
            json.dumps(skills or []),
            role_summary,
            full_jd,
            now, now,
        ),
    )
    conn.commit()
    return cur.lastrowid


def _insert_canonical(
    conn: sqlite3.Connection,
    *,
    company: str,
    title: str,
    location: str,
    team: str | None = None,
    seniority: str = "Senior",
    skills: list[str] | None = None,
    role_summary: str = "A canonical role summary.",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO canonical_postings
            (user_id, canonical_title, canonical_company, canonical_seniority,
             canonical_location, team_or_department, top_skills, role_summary,
             full_jd, full_jd_provenance, first_seen, last_seen, sources_summary)
        VALUES ('default', ?, ?, ?, ?, ?, ?, ?, '', '{}', ?, ?, '["linkedin"]')
        """,
        (
            title, company, seniority, location, team,
            json.dumps(skills or []),
            role_summary,
            now, now,
        ),
    )
    conn.commit()
    return cur.lastrowid


def _insert_embedding(
    conn: sqlite3.Connection,
    posting_id: int,
    vec: list[float],
    text_source: str = "role_summary",
) -> None:
    blob = _pack_vec(vec)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO posting_embeddings
            (posting_id, user_id, text_source, text_hash, embedding, embedding_dim,
             model_name, embedded_at)
        VALUES (?, 'default', ?, 'hash', ?, ?, 'text-embedding-3-small', ?)
        """,
        (str(posting_id), text_source, blob, len(vec), now),
    )
    conn.commit()


def _link_posting_to_canonical(
    conn: sqlite3.Connection,
    posting_id: int,
    canonical_id: int,
    merge_kind: str = "new_canonical",
) -> None:
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


# ---------------------------------------------------------------------------
# Helper: build a minimal on-disk test DB and use it with decide()
# ---------------------------------------------------------------------------


def _make_on_disk_db(tmp_path: Path) -> Path:
    """Return path to a temp SQLite DB with the full test schema."""
    db_path = tmp_path / "test.db"
    conn = _make_test_db()
    # Export to on-disk via dump + re-import
    with sqlite3.connect(str(db_path)) as disk_conn:
        for line in conn.iterdump():
            try:
                disk_conn.execute(line)
            except Exception:
                pass  # index/constraint conflicts are fine
        disk_conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Unit tests: jaccard
# ---------------------------------------------------------------------------


class TestJaccard:
    def test_identical_sets(self) -> None:
        assert jaccard({"python", "sql"}, {"python", "sql"}) == pytest.approx(1.0)

    def test_disjoint_sets(self) -> None:
        assert jaccard({"python"}, {"java"}) == pytest.approx(0.0)

    def test_partial_overlap(self) -> None:
        # intersection=1, union=3 → 1/3
        result = jaccard({"a", "b"}, {"b", "c"})
        assert result == pytest.approx(1 / 3, abs=1e-9)

    def test_empty_first_set(self) -> None:
        assert jaccard(set(), {"python"}) == pytest.approx(0.0)

    def test_empty_second_set(self) -> None:
        assert jaccard({"python"}, set()) == pytest.approx(0.0)

    def test_both_empty(self) -> None:
        assert jaccard(set(), set()) == pytest.approx(0.0)

    def test_case_insensitive(self) -> None:
        assert jaccard({"Python"}, {"python"}) == pytest.approx(1.0)

    def test_mixed_case(self) -> None:
        result = jaccard({"Machine Learning", "NLP"}, {"machine learning", "CV"})
        # intersection={machine learning}, union={machine learning, nlp, cv} → 1/3
        assert result == pytest.approx(1 / 3, abs=1e-9)


# ---------------------------------------------------------------------------
# Unit tests: seniority_match
# ---------------------------------------------------------------------------


class TestSeniorityMatch:
    def test_identical_non_null(self) -> None:
        assert seniority_match("Senior", "Senior") == pytest.approx(1.0)

    def test_different_values(self) -> None:
        assert seniority_match("Senior", "Staff") == pytest.approx(0.0)

    def test_first_null(self) -> None:
        assert seniority_match(None, "Senior") == pytest.approx(0.0)

    def test_second_null(self) -> None:
        assert seniority_match("Senior", None) == pytest.approx(0.0)

    def test_both_null(self) -> None:
        assert seniority_match(None, None) == pytest.approx(0.0)

    def test_case_insensitive(self) -> None:
        assert seniority_match("senior", "Senior") == pytest.approx(1.0)

    def test_whitespace_stripped(self) -> None:
        assert seniority_match("Senior ", " Senior") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Unit tests: title_cosine (mocked provider)
# ---------------------------------------------------------------------------


class TestTitleCosine:
    def test_none_title_returns_zero(self) -> None:
        assert title_cosine(None, "Engineer") == pytest.approx(0.0)

    def test_empty_string_returns_zero(self) -> None:
        assert title_cosine("", "Engineer") == pytest.approx(0.0)

    def test_identical_titles_high_similarity(self) -> None:
        # Use mock to avoid live API call — identical strings → identical vectors → cosine=1.0
        vec = [1.0, 0.0, 0.0]
        with patch("jd_matcher.dedup.engine._embed_title_cached", return_value=vec):
            result = title_cosine("Senior Data Scientist", "Senior Data Scientist")
        assert result == pytest.approx(1.0)

    def test_orthogonal_titles_low_similarity(self) -> None:
        def mock_embed(title: str, db_path_str: str) -> list[float]:
            if title == "Data Scientist":
                return [1.0, 0.0, 0.0]
            return [0.0, 1.0, 0.0]

        with patch("jd_matcher.dedup.engine._embed_title_cached", side_effect=mock_embed):
            result = title_cosine("Data Scientist", "Marketing Manager")
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# FUSE math tests with known inputs/outputs (AC-3)
# 5 cases covering the formula: 0.4*emb + 0.3*skills + 0.2*title + 0.1*sen
# ---------------------------------------------------------------------------


class TestFuseMath:
    """Verify the FUSE formula produces correct weighted sums."""

    def _make_posting(
        self,
        *,
        title: str = "Engineer",
        seniority: str | None = "Senior",
        skills: list[str] | None = None,
    ) -> _PostingRow:
        return _PostingRow(
            posting_id=1,
            user_id="default",
            canonical_title=title,
            canonical_company="Acme",
            canonical_seniority=seniority,
            canonical_location="Vancouver",
            team_or_department="Engineering",
            top_skills=skills or [],
            role_summary=None,
        )

    def _make_candidate(
        self,
        *,
        title: str = "Engineer",
        seniority: str | None = "Senior",
        skills: list[str] | None = None,
        canonical_id: int = 10,
    ) -> _CanonicalCandidate:
        return _CanonicalCandidate(
            canonical_id=canonical_id,
            canonical_title=title,
            canonical_company="Acme",
            canonical_seniority=seniority,
            canonical_location="Vancouver",
            team_or_department="Engineering",
            top_skills=skills or [],
            role_summary="A role.",
        )

    @pytest.fixture
    def config(self) -> DedupConfig:
        return DedupConfig(
            auto_merge_threshold=0.90,
            fuse_weight_embedding=0.4,
            fuse_weight_skills=0.3,
            fuse_weight_title=0.2,
            fuse_weight_seniority=0.1,
        )

    def _run_fuse(
        self,
        posting: _PostingRow,
        candidate: _CanonicalCandidate,
        emb_cosine: float,
        title_sim: float,
        config: DedupConfig,
    ) -> tuple[float, dict[str, float]]:
        posting_vec = np.array([1.0, 0.0], dtype=np.float32)
        canonical_vec = np.array([emb_cosine, (1 - emb_cosine**2) ** 0.5], dtype=np.float32)

        with patch("jd_matcher.dedup.engine.title_cosine", return_value=title_sim):
            score, breakdown = _compute_fuse_score(
                posting=posting,
                candidate=candidate,
                posting_vec=posting_vec,
                canonical_vec=canonical_vec,
                config=config,
                db_path=Path("/tmp/nonexistent.db"),
            )
        return score, breakdown

    def test_case1_perfect_match(self, config: DedupConfig) -> None:
        """All terms are 1.0 → total = 0.4 + 0.3 + 0.2 + 0.1 = 1.0"""
        posting = self._make_posting(skills=["python", "sql"])
        candidate = self._make_candidate(skills=["python", "sql"])
        score, bd = self._run_fuse(posting, candidate, emb_cosine=1.0, title_sim=1.0, config=config)
        assert score == pytest.approx(1.0, abs=1e-4)

    def test_case2_emb_only(self, config: DedupConfig) -> None:
        """Only emb_cosine=1.0; all others=0. → total = 0.4*1 = 0.4"""
        posting = self._make_posting(skills=[], seniority=None)
        candidate = self._make_candidate(skills=[], seniority=None)
        score, bd = self._run_fuse(posting, candidate, emb_cosine=1.0, title_sim=0.0, config=config)
        assert score == pytest.approx(0.4, abs=1e-4)

    def test_case3_skills_and_seniority(self, config: DedupConfig) -> None:
        """emb=0, title=0, skills=0.5, seniority=1.0 → total = 0.3*0.5 + 0.1*1.0 = 0.25"""
        posting = self._make_posting(skills=["python", "sql", "spark"], seniority="Senior")
        candidate = self._make_candidate(skills=["python", "spark", "scala"], seniority="Senior")
        # jaccard: intersection={python,spark}, union={python,sql,spark,scala} → 2/4=0.5
        posting_vec = np.array([0.0, 1.0], dtype=np.float32)
        canonical_vec = np.array([1.0, 0.0], dtype=np.float32)  # orthogonal → emb=0
        with patch("jd_matcher.dedup.engine.title_cosine", return_value=0.0):
            score, bd = _compute_fuse_score(
                posting=posting,
                candidate=candidate,
                posting_vec=posting_vec,
                canonical_vec=canonical_vec,
                config=config,
                db_path=Path("/tmp/nonexistent.db"),
            )
        assert score == pytest.approx(0.25, abs=1e-4)

    def test_case4_above_threshold(self, config: DedupConfig) -> None:
        """emb=0.95, skills=1.0, title=0.9, seniority=1.0
           → 0.4*0.95 + 0.3*1.0 + 0.2*0.9 + 0.1*1.0 = 0.38+0.30+0.18+0.10 = 0.96"""
        posting = self._make_posting(skills=["python", "ml"])
        candidate = self._make_candidate(skills=["python", "ml"])
        score, bd = self._run_fuse(posting, candidate, emb_cosine=0.95, title_sim=0.9, config=config)
        expected = 0.4 * 0.95 + 0.3 * 1.0 + 0.2 * 0.9 + 0.1 * 1.0
        assert score == pytest.approx(expected, abs=1e-4)
        assert score > 0.90

    def test_case5_below_threshold(self, config: DedupConfig) -> None:
        """emb=0.7, skills=0.5, title=0.6, seniority=0.0
           → 0.4*0.7 + 0.3*0.5 + 0.2*0.6 + 0.1*0.0 = 0.28+0.15+0.12+0.0 = 0.55"""
        posting = self._make_posting(skills=["python", "sql", "r"], seniority="Senior")
        candidate = self._make_candidate(skills=["python", "ml", "r"], seniority="Staff")
        # jaccard: intersection={python,r}, union={python,sql,r,ml} → 2/4=0.5
        score, bd = self._run_fuse(posting, candidate, emb_cosine=0.7, title_sim=0.6, config=config)
        expected = 0.4 * 0.7 + 0.3 * 0.5 + 0.2 * 0.6 + 0.1 * 0.0
        assert score == pytest.approx(expected, abs=1e-4)
        assert score < 0.90


# ---------------------------------------------------------------------------
# 4 User-scenario synthetic fixture tests (AC-6)
# ---------------------------------------------------------------------------


class TestUserScenarios:
    """
    Synthetic fixture tests using an on-disk temp DB and the decide() function.
    All embeddings and title_cosine are mocked to control FUSE scores precisely.
    """

    @pytest.fixture
    def tmp_db(self, tmp_path: Path) -> tuple[Path, sqlite3.Connection]:
        """Return (db_path, open connection) for scenario setup."""
        db_path = tmp_path / "dedup_test.db"
        conn = _make_test_db()
        # Persist to disk
        with sqlite3.connect(str(db_path)) as disk_conn:
            for line in conn.iterdump():
                try:
                    disk_conn.execute(line)
                except Exception:
                    pass
            disk_conn.commit()
        conn.close()
        return db_path, sqlite3.connect(str(db_path))

    def _setup_canonical_with_embedding(
        self,
        conn: sqlite3.Connection,
        db_path: Path,
        *,
        company: str,
        title: str,
        location: str,
        team: str | None,
        seniority: str,
        skills: list[str],
        vec: list[float],
    ) -> tuple[int, int]:
        """Insert canonical + a linked posting + embedding. Returns (canonical_id, posting_id)."""
        canonical_id = _insert_canonical(
            conn, company=company, title=title, location=location,
            team=team, seniority=seniority, skills=skills,
        )
        # Create a linked seed posting
        seed_posting_id = _insert_posting(
            conn, company=company, title=title, location=location,
            team=team, seniority=seniority, skills=skills,
        )
        _link_posting_to_canonical(conn, seed_posting_id, canonical_id)
        _insert_embedding(conn, seed_posting_id, vec)
        conn.commit()
        # Sync to disk
        with sqlite3.connect(str(db_path)) as disk:
            for line in conn.iterdump():
                try:
                    disk.execute(line)
                except Exception:
                    pass
            disk.commit()
        return canonical_id, seed_posting_id

    def test_scenario_i_same_company_different_teams(self, tmp_path: Path) -> None:
        """(i) Same company + different teams → BOTH shown (BLOCK separates)."""
        db_path = tmp_path / "scenario_i.db"
        conn = _make_test_db()

        # Insert canonical for "Marketing Analytics" team
        canonical_id = _insert_canonical(
            conn, company="Shopify", title="Senior Data Analyst",
            location="Vancouver", team="Marketing Analytics", seniority="Senior",
            skills=["python", "sql", "tableau"],
        )
        seed_pid = _insert_posting(
            conn, company="Shopify", title="Senior Data Analyst",
            location="Vancouver", team="Marketing Analytics", seniority="Senior",
            skills=["python", "sql", "tableau"],
        )
        _link_posting_to_canonical(conn, seed_pid, canonical_id)
        # Use a canonical-shaped embedding vector
        vec_canonical = [0.9, 0.1, 0.0, 0.0]
        _insert_embedding(conn, seed_pid, vec_canonical)
        conn.commit()

        # Create the candidate posting under "Risk Analytics" team
        candidate_pid = _insert_posting(
            conn, company="Shopify", title="Senior Data Analyst",
            location="Vancouver", team="Risk Analytics", seniority="Senior",
            skills=["python", "sql", "statistics"],
        )
        vec_candidate = [0.85, 0.15, 0.0, 0.0]
        _insert_embedding(conn, candidate_pid, vec_candidate)
        conn.commit()

        # Sync to disk
        with sqlite3.connect(str(db_path)) as disk:
            for line in conn.iterdump():
                try:
                    disk.execute(line)
                except Exception:
                    pass
            disk.commit()

        # BLOCK separates: "Risk Analytics" != "Marketing Analytics" → no BLOCK candidates
        config = DedupConfig(auto_merge_threshold=0.90)
        with patch("jd_matcher.dedup.engine.title_cosine", return_value=0.9):
            decision = decide(posting_id=candidate_pid, db_path=db_path, config=config)

        assert decision.action == "new", (
            f"Scenario (i): different-team posting should NOT merge. Got action={decision.action}"
        )
        assert decision.stage1_block_size == 0, (
            f"Scenario (i): BLOCK should be empty for different teams. Got {decision.stage1_block_size}"
        )

    def test_scenario_ii_same_team_different_roles(self, tmp_path: Path) -> None:
        """(ii) Same company + same team + different roles → BOTH shown (FUSE distinguishes)."""
        db_path = tmp_path / "scenario_ii.db"
        conn = _make_test_db()

        # Canonical: "Senior Risk Modeller (Credit)" under "Risk Analytics" at TD
        canonical_id = _insert_canonical(
            conn, company="TD Bank", title="Senior Risk Modeller (Credit)",
            location="Toronto", team="Risk Analytics", seniority="Senior",
            skills=["python", "credit risk", "sql", "sklearn"],
        )
        seed_pid = _insert_posting(
            conn, company="TD Bank", title="Senior Risk Modeller (Credit)",
            location="Toronto", team="Risk Analytics", seniority="Senior",
            skills=["python", "credit risk", "sql", "sklearn"],
        )
        _link_posting_to_canonical(conn, seed_pid, canonical_id)
        # Embedding for credit role
        vec_credit = [1.0, 0.0, 0.0, 0.0]
        _insert_embedding(conn, seed_pid, vec_credit)
        conn.commit()

        # Candidate: "Senior Risk Modeller (Operational)" — same team, different focus
        candidate_pid = _insert_posting(
            conn, company="TD Bank", title="Senior Risk Modeller (Operational)",
            location="Toronto", team="Risk Analytics", seniority="Senior",
            skills=["python", "operational risk", "sql", "pandas"],
        )
        # Operationally different → lower embedding cosine (orthogonal direction)
        vec_operational = [0.0, 1.0, 0.0, 0.0]  # cosine with credit = 0
        _insert_embedding(conn, candidate_pid, vec_operational)
        conn.commit()

        with sqlite3.connect(str(db_path)) as disk:
            for line in conn.iterdump():
                try:
                    disk.execute(line)
                except Exception:
                    pass
            disk.commit()

        config = DedupConfig(auto_merge_threshold=0.90)
        # title_cosine for "Credit" vs "Operational" → low (mock 0.4)
        # emb=0, title=0.4, skills=jaccard(credit+sql+sklearn, operational+sql+pandas)
        # intersection={python, sql}, union={python, credit risk, sql, sklearn, operational risk, pandas} → 2/6 ≈ 0.33
        # total = 0.4*0 + 0.3*0.33 + 0.2*0.4 + 0.1*1.0 = 0 + 0.099 + 0.08 + 0.1 = 0.279 < 0.90
        with patch("jd_matcher.dedup.engine.title_cosine", return_value=0.4):
            decision = decide(posting_id=candidate_pid, db_path=db_path, config=config)

        assert decision.action == "new", (
            f"Scenario (ii): different-role posting should NOT merge. Got action={decision.action}"
        )
        assert decision.stage1_block_size == 1, (
            f"Scenario (ii): BLOCK should have 1 candidate. Got {decision.stage1_block_size}"
        )
        assert decision.stage2_top_match_score < 0.90, (
            f"Scenario (ii): FUSE score should be below threshold. Got {decision.stage2_top_match_score}"
        )

    def test_scenario_iii_cross_source_same_role_merges(self, tmp_path: Path) -> None:
        """(iii) Same role + cross-source → MERGE (FUSE >= 0.90)."""
        db_path = tmp_path / "scenario_iii.db"
        conn = _make_test_db()

        # Canonical: "ML Engineer" at Shopify from LinkedIn
        canonical_id = _insert_canonical(
            conn, company="Shopify", title="ML Engineer",
            location="Vancouver", team="ML Platform", seniority="Senior",
            skills=["python", "pytorch", "mlops", "kubernetes"],
        )
        li_posting_pid = _insert_posting(
            conn, company="Shopify", title="ML Engineer",
            location="Vancouver", team="ML Platform", seniority="Senior",
            skills=["python", "pytorch", "mlops", "kubernetes"],
        )
        _link_posting_to_canonical(conn, li_posting_pid, canonical_id)
        vec_linkedin = [0.9, 0.3, 0.1, 0.0]
        _insert_embedding(conn, li_posting_pid, vec_linkedin)
        conn.commit()

        # Candidate: same "ML Engineer" from Indeed (cross-source duplicate)
        indeed_posting_pid = _insert_posting(
            conn, company="Shopify", title="ML Engineer",
            location="Vancouver", team="ML Platform", seniority="Senior",
            skills=["python", "pytorch", "mlops", "kubernetes"],
        )
        # Very similar embedding (same role same content)
        vec_indeed = [0.89, 0.31, 0.1, 0.0]
        _insert_embedding(conn, indeed_posting_pid, vec_indeed)
        conn.commit()

        with sqlite3.connect(str(db_path)) as disk:
            for line in conn.iterdump():
                try:
                    disk.execute(line)
                except Exception:
                    pass
            disk.commit()

        config = DedupConfig(auto_merge_threshold=0.90)
        # emb cosine(vec_linkedin, vec_indeed) ≈ high; skills=1.0; title=1.0; seniority=1.0
        # We mock title_cosine=1.0 to ensure total >= 0.90
        with patch("jd_matcher.dedup.engine.title_cosine", return_value=1.0):
            decision = decide(posting_id=indeed_posting_pid, db_path=db_path, config=config)

        assert decision.action == "merge", (
            f"Scenario (iii): cross-source same-role should MERGE. Got action={decision.action}"
        )
        assert decision.target_canonical_id == canonical_id
        assert decision.merge_kind == "content_dedup"
        assert decision.similarity >= 0.90

    def test_scenario_iv_same_role_different_location(self, tmp_path: Path) -> None:
        """(iv) Same company + same team + same role + different location → BOTH shown (BLOCK separates)."""
        db_path = tmp_path / "scenario_iv.db"
        conn = _make_test_db()

        # Canonical: "Data Engineer" at Lumenalta in Vancouver
        canonical_id = _insert_canonical(
            conn, company="Lumenalta", title="Data Engineer",
            location="Vancouver", team="Data Platform", seniority="Senior",
            skills=["python", "spark", "sql"],
        )
        van_pid = _insert_posting(
            conn, company="Lumenalta", title="Data Engineer",
            location="Vancouver", team="Data Platform", seniority="Senior",
            skills=["python", "spark", "sql"],
        )
        _link_posting_to_canonical(conn, van_pid, canonical_id)
        _insert_embedding(conn, van_pid, [1.0, 0.0, 0.0])
        conn.commit()

        # Candidate: same role but Toronto location
        toronto_pid = _insert_posting(
            conn, company="Lumenalta", title="Data Engineer",
            location="Toronto", team="Data Platform", seniority="Senior",
            skills=["python", "spark", "sql"],
        )
        _insert_embedding(conn, toronto_pid, [1.0, 0.0, 0.0])
        conn.commit()

        with sqlite3.connect(str(db_path)) as disk:
            for line in conn.iterdump():
                try:
                    disk.execute(line)
                except Exception:
                    pass
            disk.commit()

        config = DedupConfig(auto_merge_threshold=0.90)
        with patch("jd_matcher.dedup.engine.title_cosine", return_value=1.0):
            decision = decide(posting_id=toronto_pid, db_path=db_path, config=config)

        # BLOCK separates on canonical_location: "Toronto" != "Vancouver"
        assert decision.action == "new", (
            f"Scenario (iv): different-location posting should NOT merge. Got action={decision.action}"
        )
        assert decision.stage1_block_size == 0


# ---------------------------------------------------------------------------
# 10 different-team synthetic pairs — ZERO false merges (AC-7, SC-7)
# ---------------------------------------------------------------------------


class TestDifferentTeamRegression:
    """
    Regression-blocking: 10 synthetic posting pairs where company + location match
    but team_or_department differs.  Every pair must produce action='new' —
    ZERO false merges.
    """

    TEAM_PAIRS: list[tuple[str, str]] = [
        ("Marketing Analytics", "Risk Analytics"),
        ("Data Science", "Engineering"),
        ("ML Platform", "Data Warehouse"),
        ("People Analytics", "Finance Analytics"),
        ("Sales Analytics", "Marketing Analytics"),
        ("Platform Engineering", "ML Infrastructure"),
        ("Growth Analytics", "Product Analytics"),
        ("AI Research", "Applied ML"),
        ("Business Intelligence", "Data Engineering"),
        ("Data Governance", "ML Ops"),
    ]

    def test_zero_false_merges(self, tmp_path: Path) -> None:
        """All 10 different-team pairs must produce action='new'."""
        false_merges: list[str] = []

        for i, (team_a, team_b) in enumerate(self.TEAM_PAIRS):
            db_path = tmp_path / f"regression_pair_{i}.db"
            conn = _make_test_db()

            company = "Shopify"
            location = "Vancouver"
            seniority = "Senior"
            skills = ["python", "sql", "ml"]
            title = "Senior Data Scientist"

            # Canonical with team_a
            canonical_id = _insert_canonical(
                conn, company=company, title=title, location=location,
                team=team_a, seniority=seniority, skills=skills,
            )
            seed_pid = _insert_posting(
                conn, company=company, title=title, location=location,
                team=team_a, seniority=seniority, skills=skills,
            )
            _link_posting_to_canonical(conn, seed_pid, canonical_id)
            # High-cosine embedding — would cause false merge if BLOCK fails
            _insert_embedding(conn, seed_pid, [1.0, 0.0, 0.0])
            conn.commit()

            # Candidate with team_b
            candidate_pid = _insert_posting(
                conn, company=company, title=title, location=location,
                team=team_b, seniority=seniority, skills=skills,
            )
            _insert_embedding(conn, candidate_pid, [1.0, 0.0, 0.0])
            conn.commit()

            with sqlite3.connect(str(db_path)) as disk:
                for line in conn.iterdump():
                    try:
                        disk.execute(line)
                    except Exception:
                        pass
                disk.commit()
            conn.close()

            config = DedupConfig(auto_merge_threshold=0.90)
            with patch("jd_matcher.dedup.engine.title_cosine", return_value=1.0):
                decision = decide(posting_id=candidate_pid, db_path=db_path, config=config)

            if decision.action == "merge":
                false_merges.append(
                    f"Pair {i}: {team_a!r} vs {team_b!r} → FALSE MERGE "
                    f"(score={decision.similarity:.4f}, canonical={decision.target_canonical_id})"
                )

        assert len(false_merges) == 0, (
            f"REGRESSION FAILURE: {len(false_merges)} false merge(s) on different-team pairs:\n"
            + "\n".join(false_merges)
        )


# ---------------------------------------------------------------------------
# Safety check: full_jd-fallback short-circuit (design add-on)
# ---------------------------------------------------------------------------


class TestFullJdShortCircuit:
    def test_full_jd_text_source_short_circuits(self, tmp_path: Path) -> None:
        """Postings with text_source='full_jd' must short-circuit to action='new'."""
        db_path = tmp_path / "full_jd_test.db"
        conn = _make_test_db()

        posting_id = _insert_posting(
            conn, company="Jobright.ai", title="Data Scientist",
            location="Vancouver", skills=["python"],
        )
        # Insert embedding with text_source='full_jd' (boilerplate-inflation scenario)
        _insert_embedding(conn, posting_id, [0.95, 0.05, 0.0], text_source="full_jd")
        conn.commit()

        with sqlite3.connect(str(db_path)) as disk:
            for line in conn.iterdump():
                try:
                    disk.execute(line)
                except Exception:
                    pass
            disk.commit()
        conn.close()

        decision = decide(posting_id=posting_id, db_path=db_path)

        assert decision.action == "new"
        assert decision.target_canonical_id is None
        assert decision.similarity == 0.0
        assert decision.merge_kind == "new_canonical"
        assert decision.stage1_block_size == 0
        assert decision.stage2_top_match_score == 0.0
        assert "extraction_failed_full_jd_fallback" in decision.blocked_by

    def test_role_summary_text_source_does_not_short_circuit(self, tmp_path: Path) -> None:
        """Postings with text_source='role_summary' must proceed normally."""
        db_path = tmp_path / "role_summary_test.db"
        conn = _make_test_db()

        posting_id = _insert_posting(
            conn, company="Acme", title="Data Engineer",
            location="Vancouver", skills=["python"],
        )
        _insert_embedding(conn, posting_id, [1.0, 0.0, 0.0], text_source="role_summary")
        conn.commit()

        with sqlite3.connect(str(db_path)) as disk:
            for line in conn.iterdump():
                try:
                    disk.execute(line)
                except Exception:
                    pass
            disk.commit()
        conn.close()

        # No canonicals → action='new' but for the right reason (empty BLOCK, not short-circuit)
        decision = decide(posting_id=posting_id, db_path=db_path)
        assert decision.action == "new"
        assert "extraction_failed_full_jd_fallback" not in decision.blocked_by


# ---------------------------------------------------------------------------
# Inactive/Expired bypass (AC-5)
# ---------------------------------------------------------------------------


class TestInactiveExpiredBypass:
    def test_inactive_canonical_excluded_from_block(self, tmp_path: Path) -> None:
        """Canonicals with an applied posting in Inactive status must be excluded from BLOCK."""
        db_path = tmp_path / "inactive_test.db"
        conn = _make_test_db()

        # Create canonical + seed posting
        canonical_id = _insert_canonical(
            conn, company="Acme", title="ML Engineer",
            location="Vancouver", team="ML", seniority="Senior",
            skills=["python", "pytorch"],
        )
        seed_pid = _insert_posting(
            conn, company="Acme", title="ML Engineer",
            location="Vancouver", team="ML", seniority="Senior",
            skills=["python", "pytorch"],
        )
        _link_posting_to_canonical(conn, seed_pid, canonical_id)
        _insert_embedding(conn, seed_pid, [1.0, 0.0, 0.0])

        # Mark seed posting as Inactive — note: the applied table CHECK constraint in
        # tests uses a relaxed schema (no CHECK). In real DB, Inactive/Expired aren't valid
        # at M2 but the query is written for future-compatibility.
        # For this test, we bypass the CHECK by using a relaxed test schema.
        now = datetime.now(timezone.utc).isoformat()
        # The test schema doesn't enforce CHECK on applied.status, so insert directly:
        conn.execute(
            """
            INSERT INTO applied (posting_id, user_id, status, applied_at, status_updated_at)
            VALUES (?, 'default', 'Inactive', ?, ?)
            """,
            (seed_pid, now, now),
        )
        conn.commit()

        # Candidate posting — same BLOCK key
        candidate_pid = _insert_posting(
            conn, company="Acme", title="ML Engineer",
            location="Vancouver", team="ML", seniority="Senior",
            skills=["python", "pytorch"],
        )
        _insert_embedding(conn, candidate_pid, [1.0, 0.0, 0.0])
        conn.commit()

        with sqlite3.connect(str(db_path)) as disk:
            for line in conn.iterdump():
                try:
                    disk.execute(line)
                except Exception:
                    pass
            disk.commit()
        conn.close()

        config = DedupConfig(auto_merge_threshold=0.90)
        with patch("jd_matcher.dedup.engine.title_cosine", return_value=1.0):
            decision = decide(posting_id=candidate_pid, db_path=db_path, config=config)

        # Canonical with Inactive-linked posting is excluded → block_size=0 → action=new
        assert decision.action == "new"
        assert decision.stage1_block_size == 0


# ---------------------------------------------------------------------------
# DedupDecision JSON serialization round-trip (AC-8)
# ---------------------------------------------------------------------------


class TestDedupDecisionSerialization:
    def test_json_round_trip(self) -> None:
        """DedupDecision must serialize to JSON and deserialize back correctly."""
        original = DedupDecision(
            action="merge",
            target_canonical_id=42,
            similarity=0.95,
            merge_kind="content_dedup",
            stage1_block_size=3,
            stage2_top_match_score=0.95,
            blocked_by=["canonical_company", "team_or_department", "canonical_location"],
        )
        json_str = original.model_dump_json()
        restored = DedupDecision.model_validate_json(json_str)
        assert restored == original

    def test_new_canonical_json_round_trip(self) -> None:
        """Null target_canonical_id round-trips correctly."""
        original = DedupDecision(
            action="new",
            target_canonical_id=None,
            similarity=0.0,
            merge_kind="new_canonical",
            stage1_block_size=0,
            stage2_top_match_score=0.0,
            blocked_by=["extraction_failed_full_jd_fallback"],
        )
        json_str = original.model_dump_json()
        restored = DedupDecision.model_validate_json(json_str)
        assert restored == original
        assert restored.target_canonical_id is None

    def test_json_keys_match_spec(self) -> None:
        """All specified fields are present in the JSON output."""
        d = DedupDecision(
            action="new",
            target_canonical_id=None,
            similarity=0.0,
            merge_kind="new_canonical",
            stage1_block_size=0,
            stage2_top_match_score=0.0,
            blocked_by=[],
        )
        data = json.loads(d.model_dump_json())
        required_keys = {
            "action", "target_canonical_id", "similarity", "merge_kind",
            "stage1_block_size", "stage2_top_match_score", "blocked_by",
        }
        assert required_keys.issubset(set(data.keys()))


# ---------------------------------------------------------------------------
# BLOCK lookup unit test (uses in-memory conn directly)
# ---------------------------------------------------------------------------


class TestBlockLookup:
    def test_null_team_blocks_only_against_null(self) -> None:
        conn = _make_test_db()
        _insert_canonical(
            conn, company="Shopify", title="Data Analyst",
            location="Vancouver", team=None, seniority="Senior",
            skills=["sql"],
        )
        _insert_canonical(
            conn, company="Shopify", title="Data Analyst",
            location="Vancouver", team="Marketing Analytics", seniority="Senior",
            skills=["sql"],
        )
        conn.commit()

        # Query with NULL team → should only match the NULL-team canonical
        results = _block_lookup(
            user_id="default",
            canonical_company="Shopify",
            team_or_department=None,
            canonical_location="Vancouver",
            conn=conn,
        )
        assert len(results) == 1
        assert results[0].team_or_department is None

    def test_non_null_team_does_not_block_against_null(self) -> None:
        conn = _make_test_db()
        _insert_canonical(
            conn, company="Shopify", title="Data Analyst",
            location="Vancouver", team=None, seniority="Senior",
            skills=["sql"],
        )
        conn.commit()

        results = _block_lookup(
            user_id="default",
            canonical_company="Shopify",
            team_or_department="Engineering",
            canonical_location="Vancouver",
            conn=conn,
        )
        assert len(results) == 0

    def test_exact_case_matching(self) -> None:
        """BLOCK lookup uses exact-case SQL equality (index-friendly).
        Canonical values from C18 are consistently capitalised; same-case query matches."""
        conn = _make_test_db()
        _insert_canonical(
            conn, company="Shopify", title="Data Analyst",
            location="Vancouver", team="Marketing Analytics", seniority="Senior",
            skills=["sql"],
        )
        conn.commit()

        # Same case as stored → matches
        results = _block_lookup(
            user_id="default",
            canonical_company="Shopify",
            team_or_department="Marketing Analytics",
            canonical_location="Vancouver",
            conn=conn,
        )
        assert len(results) == 1

    def test_different_case_no_match(self) -> None:
        """Exact-case matching: all-caps query does not match title-case canonical.
        BLOCK uses index-friendly exact equality; application layer must normalise
        lookup keys to match canonical capitalisation from C18."""
        conn = _make_test_db()
        _insert_canonical(
            conn, company="Shopify", title="Data Analyst",
            location="Vancouver", team="Marketing Analytics", seniority="Senior",
            skills=["sql"],
        )
        conn.commit()

        # Different case → no match (application normalisation is caller's responsibility)
        results = _block_lookup(
            user_id="default",
            canonical_company="SHOPIFY",
            team_or_department="Marketing Analytics",
            canonical_location="VANCOUVER",
            conn=conn,
        )
        # Expected: 0 — exact-case SQL equality; C18 stores title-case
        assert len(results) == 0
