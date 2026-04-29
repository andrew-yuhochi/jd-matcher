"""C21 — Two-Stage Dedup Engine: BLOCK + FUSE.

Public API:
    decide(posting_id, db_path=None, provider=None) -> DedupDecision

Stage 1 — BLOCK: query canonical_postings on (user_id, canonical_company,
    team_or_department, canonical_location) using idx_canonical_user_block.
    NULL team_or_department blocks ONLY against other NULLs.
    Inactive/Expired bypass: excludes canonicals where any linked posting has
    applied.status IN ('Inactive', 'Expired') — no-op at M2; load-bearing at MVP-M1.

Stage 2 — FUSE: for each BLOCK candidate compute:
    total = 0.4*emb_cosine + 0.3*skills_jaccard + 0.2*title_cosine + 0.1*seniority_match
    Weights are config-driven (config/dedup.yaml: dedup.fuse_weight_*).
    NULL terms contribute 0 — no weight renormalization (safe default: degraded
    data → lower score → less likely to merge).

Safety check (Step 0): postings whose posting_embeddings.text_source='full_jd'
    are short-circuited to action='new' before BLOCK runs.
    Rationale (post-M2-007 investigation): full_jd embeddings are dominated by
    company/staffing-firm boilerplate, inflating cosines by ~0.30 and causing
    false-merge risk on genuinely different roles.

C21 is a pure decision function — it NEVER writes to canonical_postings or
posting_canonical_links. Merge application is C29's responsibility (M2-009).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import yaml
from pydantic import BaseModel

from jd_matcher.llm.embed import cosine

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"
# config/dedup.yaml is relative to project root: engine.py is 4 levels deep
# src/jd_matcher/dedup/engine.py → dedup/ → jd_matcher/ → src/ → project root
_DEFAULT_DEDUP_CONFIG_PATH = Path(__file__).parents[3] / "config" / "dedup.yaml"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DedupConfig:
    auto_merge_threshold: float = 0.90
    fuse_weight_embedding: float = 0.4
    fuse_weight_skills: float = 0.3
    fuse_weight_title: float = 0.2
    fuse_weight_seniority: float = 0.1


def _load_dedup_config(path: Path | None = None) -> DedupConfig:
    resolved = path if path is not None else _DEFAULT_DEDUP_CONFIG_PATH
    if not resolved.exists():
        logger.debug("dedup config not found at %s — using defaults", resolved)
        return DedupConfig()
    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        dedup_raw = raw.get("dedup", {})
        return DedupConfig(
            auto_merge_threshold=float(dedup_raw.get("auto_merge_threshold", 0.90)),
            fuse_weight_embedding=float(dedup_raw.get("fuse_weight_embedding", 0.4)),
            fuse_weight_skills=float(dedup_raw.get("fuse_weight_skills", 0.3)),
            fuse_weight_title=float(dedup_raw.get("fuse_weight_title", 0.2)),
            fuse_weight_seniority=float(dedup_raw.get("fuse_weight_seniority", 0.1)),
        )
    except Exception as exc:
        logger.warning("dedup config parse error (%s) — using defaults", exc)
        return DedupConfig()


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class DedupDecision(BaseModel):
    """Result of C21's two-stage dedup evaluation for a single posting."""

    action: Literal["merge", "new"]
    target_canonical_id: int | None
    similarity: float
    merge_kind: Literal["content_dedup", "repost", "new_canonical"]
    stage1_block_size: int
    stage2_top_match_score: float
    blocked_by: list[str]


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------


@dataclass
class _CanonicalCandidate:
    canonical_id: int
    canonical_title: str | None
    canonical_company: str
    canonical_seniority: str | None
    canonical_location: str
    team_or_department: str | None
    top_skills: list[str]  # decoded from JSON
    role_summary: str | None


@dataclass
class _PostingRow:
    posting_id: int
    user_id: str
    canonical_title: str | None
    canonical_company: str | None
    canonical_seniority: str | None  # postings.seniority_band
    canonical_location: str | None
    team_or_department: str | None
    top_skills: list[str]
    role_summary: str | None


# ---------------------------------------------------------------------------
# Pure similarity helpers
# ---------------------------------------------------------------------------


def jaccard(s1: set[str], s2: set[str]) -> float:
    """Set Jaccard similarity, with both sides lowercased.

    Returns 0.0 when either set is empty (intersection is always 0 in that case).
    """
    a = {x.lower() for x in s1}
    b = {x.lower() for x in s2}
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def seniority_match(s1: str | None, s2: str | None) -> float:
    """Return 1.0 iff both strings are non-None AND identical, else 0.0."""
    if s1 is None or s2 is None:
        return 0.0
    return 1.0 if s1.strip().lower() == s2.strip().lower() else 0.0


# ---------------------------------------------------------------------------
# Title cosine (cached) — uses EmbeddingProvider for short strings
# ---------------------------------------------------------------------------


@lru_cache(maxsize=512)
def _embed_title_cached(title: str, db_path_str: str) -> list[float]:
    """Return the embedding vector for a title string (cached by title+db_path).

    Uses the default EmbeddingProvider (C28) — the same model as role_summary
    embeddings, so vectors are directly comparable.
    """
    from jd_matcher.llm.providers.factory import make_embedder

    provider = make_embedder(db_path=Path(db_path_str) if db_path_str else None)
    vectors, _ = provider.embed([title])
    return vectors[0]


def title_cosine(t1: str | None, t2: str | None, db_path: Path | None = None) -> float:
    """Cosine similarity between two canonical_title embeddings.

    Returns 0.0 when either title is None or empty.
    Embeddings are cached per (title, db_path) to avoid redundant API calls
    within a single pipeline run.
    """
    if not t1 or not t2:
        return 0.0
    db_str = str(db_path) if db_path else str(_DEFAULT_DB_PATH)
    v1 = _embed_title_cached(t1, db_str)
    v2 = _embed_title_cached(t2, db_str)
    return cosine(v1, v2)


# ---------------------------------------------------------------------------
# Stage 1 — BLOCK lookup
# ---------------------------------------------------------------------------


def _block_lookup(
    *,
    user_id: str,
    canonical_company: str,
    team_or_department: str | None,
    canonical_location: str,
    conn: sqlite3.Connection,
) -> list[_CanonicalCandidate]:
    """Query canonical_postings for BLOCK candidates.

    Issues a single exact-case SQL query against idx_canonical_user_block
    (user_id, canonical_company, team_or_department, canonical_location).
    Case normalisation is the caller's responsibility — LOWER() / COLLATE
    NOCASE in SQL would defeat the index scan (TDD §C21).  In practice,
    C18 LLM extraction emits consistent capitalisation so exact-case
    matching handles all real lookups correctly.  NULL team_or_department
    blocks ONLY against other NULLs (strict by design, per TDD §C21).

    The NOT EXISTS clause excludes canonicals where any linked posting has
    applied.status IN ('Inactive', 'Expired').  No-op at M2; load-bearing
    at MVP-M1 when those statuses are introduced.

    See TestBlockLookup in tests/dedup/test_engine.py for behaviour
    verification, including the case-sensitivity contract.
    """
    _NOT_EXISTS = """
        AND NOT EXISTS (
            SELECT 1
            FROM posting_canonical_links pcl
            JOIN applied a ON a.posting_id = pcl.posting_id
            WHERE pcl.canonical_id = canonical_postings.canonical_id
              AND a.status IN ('Inactive', 'Expired')
        )
    """
    _SELECT_COLS = (
        "SELECT canonical_id, canonical_title, canonical_company, "
        "canonical_seniority, canonical_location, team_or_department, "
        "top_skills, role_summary FROM canonical_postings "
    )

    if team_or_department is None:
        sql = (
            _SELECT_COLS
            + "WHERE user_id = ? AND canonical_company = ? AND team_or_department IS NULL"
            + "  AND canonical_location = ?"
            + _NOT_EXISTS
        )
        params = (user_id, canonical_company, canonical_location)
    else:
        sql = (
            _SELECT_COLS
            + "WHERE user_id = ? AND canonical_company = ? AND team_or_department = ?"
            + "  AND canonical_location = ?"
            + _NOT_EXISTS
        )
        params = (user_id, canonical_company, team_or_department, canonical_location)

    rows = conn.execute(sql, params).fetchall()
    candidates = []
    for row in rows:
        raw_skills = row[6]
        try:
            skills: list[str] = json.loads(raw_skills) if raw_skills else []
        except (json.JSONDecodeError, TypeError):
            skills = []
        candidates.append(
            _CanonicalCandidate(
                canonical_id=row[0],
                canonical_title=row[1],
                canonical_company=row[2],
                canonical_seniority=row[3],
                canonical_location=row[4],
                team_or_department=row[5],
                top_skills=skills,
                role_summary=row[7],
            )
        )
    return candidates


# ---------------------------------------------------------------------------
# Stage 2 — FUSE scoring
# ---------------------------------------------------------------------------


def _load_embedding_vector(posting_id: int, conn: sqlite3.Connection) -> np.ndarray | None:
    """Load the embedding vector for a posting_id from posting_embeddings."""
    row = conn.execute(
        "SELECT embedding, embedding_dim FROM posting_embeddings WHERE posting_id = ?",
        (str(posting_id),),
    ).fetchone()
    if row is None:
        return None
    blob, dim = row
    vec = np.frombuffer(blob, dtype=np.float32)
    if len(vec) != dim:
        logger.warning(
            "dedup: posting %d embedding dim mismatch: blob=%d, declared=%d",
            posting_id,
            len(vec),
            dim,
        )
    return vec


def _load_canonical_embedding(canonical_id: int, conn: sqlite3.Connection) -> np.ndarray | None:
    """Load the embedding vector for a canonical via its best (newest) linked posting."""
    row = conn.execute(
        """
        SELECT pe.embedding, pe.embedding_dim
        FROM posting_canonical_links pcl
        JOIN posting_embeddings pe ON pe.posting_id = pcl.posting_id
        WHERE pcl.canonical_id = ?
          AND pe.text_source = 'role_summary'
        ORDER BY pcl.merged_at DESC
        LIMIT 1
        """,
        (canonical_id,),
    ).fetchone()
    if row is None:
        # Fallback: any text_source
        row = conn.execute(
            """
            SELECT pe.embedding, pe.embedding_dim
            FROM posting_canonical_links pcl
            JOIN posting_embeddings pe ON pe.posting_id = pcl.posting_id
            WHERE pcl.canonical_id = ?
            ORDER BY pcl.merged_at DESC
            LIMIT 1
            """,
            (canonical_id,),
        ).fetchone()
    if row is None:
        return None
    blob, dim = row
    return np.frombuffer(blob, dtype=np.float32)


def _compute_fuse_score(
    *,
    posting: _PostingRow,
    candidate: _CanonicalCandidate,
    posting_vec: np.ndarray | None,
    canonical_vec: np.ndarray | None,
    config: DedupConfig,
    db_path: Path,
) -> tuple[float, dict[str, float]]:
    """Compute the weighted fuse similarity between a posting and a canonical candidate.

    When a term is NULL/missing, it contributes 0 to the total.
    Weights are NOT renormalized — degraded data yields a lower total score,
    which reduces the chance of a false merge.  This is the safe default.

    Returns:
        (total_score, per_term_breakdown)
    """
    # Embedding cosine
    if posting_vec is not None and canonical_vec is not None:
        emb_sim = float(cosine(posting_vec, canonical_vec))
    else:
        emb_sim = 0.0

    # Skills Jaccard
    posting_skills = set(posting.top_skills)
    canonical_skills = set(candidate.top_skills)
    skills_sim = jaccard(posting_skills, canonical_skills)

    # Title cosine (cached, uses EmbeddingProvider)
    t_sim = title_cosine(posting.canonical_title, candidate.canonical_title, db_path=db_path)

    # Seniority exact match
    sen_sim = seniority_match(posting.canonical_seniority, candidate.canonical_seniority)

    total = (
        config.fuse_weight_embedding * emb_sim
        + config.fuse_weight_skills * skills_sim
        + config.fuse_weight_title * t_sim
        + config.fuse_weight_seniority * sen_sim
    )

    breakdown = {
        "emb_cosine": emb_sim,
        "skills_jaccard": skills_sim,
        "title_cosine": t_sim,
        "seniority_match": sen_sim,
        "total": total,
    }
    return total, breakdown


# ---------------------------------------------------------------------------
# Main decision function
# ---------------------------------------------------------------------------


def decide(
    posting_id: int,
    db_path: Path | None = None,
    config: DedupConfig | None = None,
    config_path: Path | None = None,
) -> DedupDecision:
    """Run the two-stage dedup algorithm for a single posting.

    Returns a DedupDecision without writing anything to the database.
    All writes (canonical record creation / merge) are handled by C29 (M2-009).

    Args:
        posting_id: ID of the candidate posting in the postings table.
        db_path:    Path to the SQLite DB (defaults to ~/.jd-matcher/jd-matcher.db).
        config:     DedupConfig override (useful in tests to avoid file I/O).
        config_path: Path to dedup.yaml override (used when config=None).

    Raises:
        ValueError: When posting_id is not found in the DB.
    """
    resolved_db = db_path or _DEFAULT_DB_PATH
    cfg = config or _load_dedup_config(config_path)

    conn = sqlite3.connect(resolved_db)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        # ----------------------------------------------------------------
        # Step 0 — Safety check: full_jd-fallback embeddings are unreliable.
        # Postings embedded from raw full_jd text (extraction failed) have
        # embeddings dominated by boilerplate, inflating cosines by ~0.30.
        # ----------------------------------------------------------------
        emb_row = conn.execute(
            "SELECT text_source FROM posting_embeddings WHERE posting_id = ?",
            (str(posting_id),),
        ).fetchone()

        if emb_row is not None and emb_row[0] == "full_jd":
            logger.info(
                "dedup: posting %d has text_source='full_jd' — short-circuiting to new "
                "(boilerplate-inflation risk)",
                posting_id,
            )
            return DedupDecision(
                action="new",
                target_canonical_id=None,
                similarity=0.0,
                merge_kind="new_canonical",
                stage1_block_size=0,
                stage2_top_match_score=0.0,
                blocked_by=["extraction_failed_full_jd_fallback"],
            )

        # ----------------------------------------------------------------
        # Fetch the candidate posting row
        # ----------------------------------------------------------------
        posting_row = conn.execute(
            """
            SELECT id, user_id, canonical_title, canonical_company, canonical_location,
                   team_or_department, seniority_band, top_skills
            FROM postings
            WHERE id = ?
            """,
            (posting_id,),
        ).fetchone()
        if posting_row is None:
            raise ValueError(f"Posting {posting_id} not found in DB")

        pid, user_id, title, company, location, team, seniority, raw_skills = posting_row
        try:
            skills: list[str] = json.loads(raw_skills) if raw_skills else []
        except (json.JSONDecodeError, TypeError):
            skills = []

        posting = _PostingRow(
            posting_id=pid,
            user_id=user_id or "default",
            canonical_title=title,
            canonical_company=company or "",
            canonical_seniority=seniority,
            canonical_location=location or "",
            team_or_department=team,
            top_skills=skills,
            role_summary=None,  # not needed directly; embedding loaded from posting_embeddings
        )

        if not posting.canonical_company or not posting.canonical_location:
            logger.info(
                "dedup: posting %d missing canonical_company or canonical_location — action=new",
                posting_id,
            )
            return DedupDecision(
                action="new",
                target_canonical_id=None,
                similarity=0.0,
                merge_kind="new_canonical",
                stage1_block_size=0,
                stage2_top_match_score=0.0,
                blocked_by=["missing_block_key"],
            )

        # ----------------------------------------------------------------
        # Stage 1 — BLOCK
        # ----------------------------------------------------------------
        blocked_by_fields = ["canonical_company", "team_or_department", "canonical_location"]
        candidates = _block_lookup(
            user_id=posting.user_id,
            canonical_company=posting.canonical_company,
            team_or_department=posting.team_or_department,
            canonical_location=posting.canonical_location,
            conn=conn,
        )
        block_size = len(candidates)

        logger.info(
            "dedup: posting %d stage1_block_size=%d (company=%s, team=%s, location=%s)",
            posting_id,
            block_size,
            posting.canonical_company,
            posting.team_or_department,
            posting.canonical_location,
        )

        if not candidates:
            return DedupDecision(
                action="new",
                target_canonical_id=None,
                similarity=0.0,
                merge_kind="new_canonical",
                stage1_block_size=0,
                stage2_top_match_score=0.0,
                blocked_by=blocked_by_fields,
            )

        # ----------------------------------------------------------------
        # Stage 2 — FUSE
        # ----------------------------------------------------------------
        posting_vec = _load_embedding_vector(posting_id, conn)
        if posting_vec is None:
            logger.info(
                "dedup: posting %d has no embedding — treating as missing (action=new)",
                posting_id,
            )

        best_score = 0.0
        best_candidate_id: int | None = None
        best_breakdown: dict[str, float] = {}

        for cand in candidates:
            canonical_vec = _load_canonical_embedding(cand.canonical_id, conn)
            score, breakdown = _compute_fuse_score(
                posting=posting,
                candidate=cand,
                posting_vec=posting_vec,
                canonical_vec=canonical_vec,
                config=cfg,
                db_path=resolved_db,
            )

            logger.debug(
                "dedup: posting %d vs canonical %d: score=%.4f breakdown=%s",
                posting_id,
                cand.canonical_id,
                score,
                breakdown,
            )

            if score > best_score:
                best_score = score
                best_candidate_id = cand.canonical_id
                best_breakdown = breakdown

        logger.info(
            "dedup: posting %d stage2_top_match=%.4f (threshold=%.2f) best_canonical=%s",
            posting_id,
            best_score,
            cfg.auto_merge_threshold,
            best_candidate_id,
        )

        if best_score >= cfg.auto_merge_threshold and best_candidate_id is not None:
            return DedupDecision(
                action="merge",
                target_canonical_id=best_candidate_id,
                similarity=best_score,
                merge_kind="content_dedup",
                stage1_block_size=block_size,
                stage2_top_match_score=best_score,
                blocked_by=blocked_by_fields,
            )
        else:
            return DedupDecision(
                action="new",
                target_canonical_id=None,
                similarity=best_score,
                merge_kind="new_canonical",
                stage1_block_size=block_size,
                stage2_top_match_score=best_score,
                blocked_by=blocked_by_fields,
            )
    finally:
        conn.close()
