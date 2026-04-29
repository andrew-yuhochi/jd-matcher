"""Tests for C20 — Embedding Pipeline (TASK-M2-007).

Unit tests (always run):
  - _select_text_source selection logic
  - _pack_embedding / _unpack_embedding round-trip
  - cache lookup logic (mocked provider)
  - batch dedup logic (mocked provider — same text_hash → single call)

Live tests (gated by SKIP_LIVE):
  - Synthetic cosine sanity: 5 near-duplicate pairs → cosine ≥ 0.85
  - Anti-test: 5 different-role pairs → cosine ≤ 0.70
  - Live integration: embed real posting_id 91 → dim 1536 + non-zero

Run all tests:
    SKIP_LIVE=0 .venv/bin/python -m pytest tests/llm/test_embed.py -v

Estimated live cost: ~10 embedding calls × ~100 tokens × $0.00002/1k ≈ $0.00002 total
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.llm.embed import (
    PostingEmbedding,
    _pack_embedding,
    _select_text_source,
    _sha256,
    _unpack_embedding,
    cosine,
    embed_posting,
    embed_postings_batch,
)
from jd_matcher.llm.providers.base import EmbeddingMetadata

SKIP_LIVE = os.environ.get("SKIP_LIVE", "1") == "1"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_provider_mock(dim: int = 1536) -> MagicMock:
    """Return a mock EmbeddingProvider that returns random unit vectors."""

    def _embed(texts: list[str]):
        rng = np.random.default_rng(seed=abs(hash(texts[0])) % (2**31))
        vectors = [rng.random(dim).tolist() for _ in texts]
        meta = EmbeddingMetadata(input_tokens=len(texts) * 10, latency_ms=50, cost_usd=0.0)
        return vectors, meta

    mock = MagicMock()
    mock.model = "text-embedding-3-small"
    mock.embed.side_effect = _embed
    return mock


def _init_db_with_postings(
    db_path: Path,
    postings: list[dict],
) -> None:
    """Create a minimal test DB with given postings rows."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        for p in postings:
            conn.execute(
                """
                INSERT INTO postings
                    (id, role_summary, full_jd, first_seen, last_seen, hydration_status)
                VALUES (?, ?, ?, '2026-01-01', '2026-01-01', 'complete')
                """,
                (p["id"], p.get("role_summary"), p.get("full_jd")),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Unit tests — _select_text_source
# ---------------------------------------------------------------------------


def test_select_text_source_prefers_role_summary() -> None:
    row = {"role_summary": "Summary text", "full_jd": "Full JD text"}
    result = _select_text_source(row)
    assert result is not None
    text, source = result
    assert text == "Summary text"
    assert source == "role_summary"


def test_select_text_source_falls_back_to_full_jd() -> None:
    row = {"role_summary": "", "full_jd": "Full JD text"}
    result = _select_text_source(row)
    assert result is not None
    text, source = result
    assert text == "Full JD text"
    assert source == "full_jd"


def test_select_text_source_none_when_both_empty() -> None:
    row = {"role_summary": "", "full_jd": ""}
    assert _select_text_source(row) is None


def test_select_text_source_none_when_both_none() -> None:
    row = {"role_summary": None, "full_jd": None}
    assert _select_text_source(row) is None


def test_select_text_source_strips_whitespace() -> None:
    row = {"role_summary": "   ", "full_jd": "Fallback JD"}
    result = _select_text_source(row)
    assert result is not None
    _, source = result
    assert source == "full_jd"


# ---------------------------------------------------------------------------
# Unit tests — _pack_embedding / _unpack_embedding round-trip
# ---------------------------------------------------------------------------


def test_pack_unpack_round_trip() -> None:
    original = np.random.default_rng(42).random(1536).astype(np.float32)
    blob = _pack_embedding(original)
    recovered = _unpack_embedding(blob)
    assert recovered.dtype == np.float32
    assert len(recovered) == 1536
    np.testing.assert_array_almost_equal(original, recovered, decimal=6)


def test_pack_produces_correct_byte_count() -> None:
    vec = np.zeros(1536, dtype=np.float32)
    blob = _pack_embedding(vec)
    assert len(blob) == 1536 * 4  # 4 bytes per float32


def test_pack_non_1536_dim() -> None:
    vec = np.ones(384, dtype=np.float32)
    blob = _pack_embedding(vec)
    recovered = _unpack_embedding(blob)
    assert len(recovered) == 384


# ---------------------------------------------------------------------------
# Unit tests — cosine helper
# ---------------------------------------------------------------------------


def test_cosine_identical_vectors() -> None:
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert cosine(v, v) == pytest.approx(1.0, abs=1e-6)


def test_cosine_orthogonal_vectors() -> None:
    v1 = np.array([1.0, 0.0], dtype=np.float32)
    v2 = np.array([0.0, 1.0], dtype=np.float32)
    assert cosine(v1, v2) == pytest.approx(0.0, abs=1e-6)


def test_cosine_opposite_vectors() -> None:
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert cosine(v, -v) == pytest.approx(-1.0, abs=1e-6)


def test_cosine_zero_vector_returns_zero() -> None:
    v1 = np.zeros(10, dtype=np.float32)
    v2 = np.ones(10, dtype=np.float32)
    assert cosine(v1, v2) == 0.0


def test_cosine_accepts_lists() -> None:
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert cosine(v1, v2) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Unit tests — embed_posting cache behaviour (mocked provider)
# ---------------------------------------------------------------------------


def test_embed_posting_writes_embedding_row(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _init_db_with_postings(db_path, [{"id": 1, "role_summary": "Some role summary text", "full_jd": None}])
    mock_provider = _make_provider_mock()

    result = embed_posting(1, db_path=db_path, provider=mock_provider)

    assert result.posting_id == 1
    assert result.text_source == "role_summary"
    assert result.embedding_dim == 1536
    assert len(result.embedding) == 1536
    assert result.model_name == "text-embedding-3-small"
    mock_provider.embed.assert_called_once()


def test_embed_posting_cache_hit_skips_provider(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _init_db_with_postings(db_path, [{"id": 1, "role_summary": "Cached role summary", "full_jd": None}])
    mock_provider = _make_provider_mock()

    # First call — goes to provider
    embed_posting(1, db_path=db_path, provider=mock_provider)
    assert mock_provider.embed.call_count == 1

    # Second call — should hit cache (no extra provider call)
    result = embed_posting(1, db_path=db_path, provider=mock_provider)
    assert mock_provider.embed.call_count == 1  # still 1 — cache hit
    assert result.posting_id == 1


def test_embed_posting_cache_hit_writes_cache_hit_ledger_row(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _init_db_with_postings(db_path, [{"id": 1, "role_summary": "Cache test text", "full_jd": None}])
    mock_provider = _make_provider_mock()

    embed_posting(1, db_path=db_path, provider=mock_provider)
    embed_posting(1, db_path=db_path, provider=mock_provider)

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT status FROM llm_call_ledger WHERE call_kind='embedding' ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    statuses = [r[0] for r in rows]
    assert "cache_hit" in statuses


def test_embed_posting_raises_on_missing_posting(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    mock_provider = _make_provider_mock()

    with pytest.raises(ValueError, match="not found in DB"):
        embed_posting(999, db_path=db_path, provider=mock_provider)


def test_embed_posting_raises_on_empty_text(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _init_db_with_postings(db_path, [{"id": 1, "role_summary": "", "full_jd": ""}])
    mock_provider = _make_provider_mock()

    with pytest.raises(ValueError, match="empty"):
        embed_posting(1, db_path=db_path, provider=mock_provider)


def test_embed_posting_vector_dim_is_1536(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _init_db_with_postings(db_path, [{"id": 1, "role_summary": "Test JD text", "full_jd": None}])
    mock_provider = _make_provider_mock(dim=1536)

    result = embed_posting(1, db_path=db_path, provider=mock_provider)
    assert result.embedding_dim == 1536
    assert len(result.embedding) == 1536


# ---------------------------------------------------------------------------
# Unit tests — embed_postings_batch dedup (mocked provider)
# ---------------------------------------------------------------------------


def test_batch_dedup_same_text_hash_single_call(tmp_path: Path) -> None:
    """Two postings with identical text → single provider call (batch dedup AC)."""
    shared_text = "Identical role summary text shared by both postings"
    db_path = tmp_path / "test.db"
    _init_db_with_postings(
        db_path,
        [
            {"id": 1, "role_summary": shared_text, "full_jd": None},
            {"id": 2, "role_summary": shared_text, "full_jd": None},
        ],
    )
    mock_provider = _make_provider_mock()

    results = embed_postings_batch([1, 2], db_path=db_path, provider=mock_provider)

    assert len(results) == 2
    # Only 1 API call for 1 unique text (batch dedup)
    mock_provider.embed.assert_called_once()
    call_args = mock_provider.embed.call_args[0][0]
    assert len(call_args) == 1  # single text in the call


def test_batch_dedup_different_text_makes_two_calls(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _init_db_with_postings(
        db_path,
        [
            {"id": 1, "role_summary": "First unique role summary text", "full_jd": None},
            {"id": 2, "role_summary": "Second unique role summary text", "full_jd": None},
        ],
    )
    mock_provider = _make_provider_mock()

    results = embed_postings_batch([1, 2], db_path=db_path, provider=mock_provider)

    assert len(results) == 2
    mock_provider.embed.assert_called_once()
    call_args = mock_provider.embed.call_args[0][0]
    assert len(call_args) == 2  # 2 unique texts → 1 batch call with 2 inputs


def test_batch_skips_empty_text_postings(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _init_db_with_postings(
        db_path,
        [
            {"id": 1, "role_summary": "Valid text", "full_jd": None},
            {"id": 2, "role_summary": "", "full_jd": ""},
        ],
    )
    mock_provider = _make_provider_mock()

    results = embed_postings_batch([1, 2], db_path=db_path, provider=mock_provider)

    assert len(results) == 1  # posting 2 skipped
    assert results[0].posting_id == 1


def test_batch_all_cache_hits_no_provider_call(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _init_db_with_postings(
        db_path,
        [
            {"id": 1, "role_summary": "Pre-cached role summary", "full_jd": None},
        ],
    )
    mock_provider = _make_provider_mock()

    # Prime cache
    embed_postings_batch([1], db_path=db_path, provider=mock_provider)
    assert mock_provider.embed.call_count == 1

    # Second call — all cache hits
    results = embed_postings_batch([1], db_path=db_path, provider=mock_provider)
    assert mock_provider.embed.call_count == 1  # no new provider calls
    assert len(results) == 1


# ---------------------------------------------------------------------------
# Live tests — cosine sanity (real OpenAI embeddings)
# ---------------------------------------------------------------------------

# 5 near-duplicate pairs: paraphrased but semantically identical JDs
_DUP_PAIRS = [
    (
        "Senior Machine Learning Engineer with experience in Python, TensorFlow, and model deployment on cloud platforms including AWS.",
        "Senior ML Engineer proficient in Python and TensorFlow. Experienced in deploying machine learning models to cloud environments like AWS.",
    ),
    (
        "Data Scientist role requiring strong SQL and Python skills for analytics and A/B testing at a fintech company.",
        "Data Scientist at a fintech firm. Strong Python and SQL background needed for A/B test analysis and data analytics.",
    ),
    (
        "MLOps engineer building Kubernetes-based model deployment infrastructure and CI/CD pipelines for machine learning workloads.",
        "Machine learning infrastructure engineer maintaining Kubernetes model serving, CI/CD pipelines, and MLOps tooling for production ML.",
    ),
    (
        "NLP research engineer to develop large language models and fine-tune transformers for text classification and summarization.",
        "NLP engineer: fine-tune transformer-based language models for classification and summarization tasks in production.",
    ),
    (
        "Senior Data Engineer building Spark pipelines and data warehouse infrastructure on AWS for a machine learning platform.",
        "Data platform engineer: design and maintain Spark-based ETL pipelines and AWS data warehouse for ML workloads.",
    ),
]

# 5 different-role pairs: clearly distinct job descriptions
_ANTI_PAIRS = [
    (
        "Senior Accountant to manage financial statements, audits, and regulatory compliance for a mid-size enterprise.",
        "Computer Vision engineer building object detection models for autonomous vehicle perception systems.",
    ),
    (
        "Marketing Manager to lead brand campaigns, social media strategy, and content creation for consumer products.",
        "Data Infrastructure Engineer: Spark, Kafka, and Airflow pipelines for petabyte-scale data warehouse.",
    ),
    (
        "HR Business Partner for talent acquisition, employee relations, and organizational development programs.",
        "Quantitative Researcher building statistical trading models and backtesting frameworks for a hedge fund.",
    ),
    (
        "Supply Chain Analyst to optimize logistics, vendor management, and inventory forecasting for retail operations.",
        "Senior iOS Engineer building user-facing mobile features and maintaining the Swift/SwiftUI codebase.",
    ),
    (
        "Clinical Research Coordinator managing patient trials, IRB submissions, and pharmacovigilance reporting.",
        "Machine Learning Infrastructure Engineer: GPU cluster management, distributed training, model serving at scale.",
    ),
]


@pytest.mark.skipif(SKIP_LIVE, reason="SKIP_LIVE=1 — set SKIP_LIVE=0 to run live tests")
def test_cosine_sanity_dup_pairs() -> None:
    """5 near-duplicate pairs should all have cosine ≥ 0.85."""
    from jd_matcher.llm.providers.factory import make_embedder

    provider = make_embedder(db_path=None)

    scores = []
    for text_a, text_b in _DUP_PAIRS:
        vectors, _ = provider.embed([text_a, text_b])
        score = cosine(vectors[0], vectors[1])
        scores.append(score)

    print("\nDuplicate pair cosine scores:")
    for i, (pair, score) in enumerate(zip(_DUP_PAIRS, scores)):
        print(f"  pair {i+1}: {score:.4f}")

    for i, score in enumerate(scores):
        assert score >= 0.85, (
            f"Dup pair {i+1} cosine={score:.4f} < 0.85. "
            "Flag for role_summary neutralisation review — not an embedding bug per TDD §C20."
        )


@pytest.mark.skipif(SKIP_LIVE, reason="SKIP_LIVE=1 — set SKIP_LIVE=0 to run live tests")
def test_cosine_anti_pairs_different_roles() -> None:
    """5 different-role pairs should all have cosine ≤ 0.70."""
    from jd_matcher.llm.providers.factory import make_embedder

    provider = make_embedder(db_path=None)

    scores = []
    for text_a, text_b in _ANTI_PAIRS:
        vectors, _ = provider.embed([text_a, text_b])
        score = cosine(vectors[0], vectors[1])
        scores.append(score)

    print("\nAnti-pair cosine scores (different roles):")
    for i, (pair, score) in enumerate(zip(_ANTI_PAIRS, scores)):
        print(f"  pair {i+1}: {score:.4f}")

    for i, score in enumerate(scores):
        assert score <= 0.70, (
            f"Anti-pair {i+1} cosine={score:.4f} > 0.70 — "
            "unexpectedly high similarity between dissimilar roles."
        )


@pytest.mark.skipif(SKIP_LIVE, reason="SKIP_LIVE=1 — set SKIP_LIVE=0 to run live tests")
def test_live_embed_real_posting() -> None:
    """Embed real posting_id 91 and verify dim=1536 and non-zero vector."""
    db_path = Path.home() / ".jd-matcher" / "jd-matcher.db"

    result = embed_posting(91, db_path=db_path)

    assert result.posting_id == 91
    assert result.embedding_dim == 1536
    assert len(result.embedding) == 1536
    # Non-zero check: at least some elements should be non-zero
    vec = np.array(result.embedding, dtype=np.float32)
    assert np.any(vec != 0.0), "Embedding vector is all zeros — provider likely failed"
    # Magnitude should be > 0
    assert float(np.linalg.norm(vec)) > 0.0

    print(f"\nLive embed posting_id=91: dim={result.embedding_dim}, "
          f"source={result.text_source}, model={result.model_name}")
