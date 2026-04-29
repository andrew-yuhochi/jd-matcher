"""C20 — Embedding Pipeline: embed role_summary via EmbeddingProvider; store in posting_embeddings.

Public API:
    embed_posting(posting_id, db_path=None, provider=None) -> PostingEmbedding
    embed_postings_batch(posting_ids, db_path=None, provider=None) -> list[PostingEmbedding]
    cosine(v1, v2) -> float

Cache strategy:
  - SHA-256(text) + model_name pair as cache key per posting.
  - Batch dedup: postings sharing the same text_hash within one batch make a
    single provider call; all rows reference the same vector.
  - Persistent cache: posting_embeddings row with matching posting_id + text_hash
    + model_name is a cache hit (no API call, ledger row written with status='cache_hit').
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Literal

import numpy as np
from pydantic import BaseModel

from jd_matcher.llm.providers.base import EmbeddingMetadata, EmbeddingProvider

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"
_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIM = 1536


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class PostingEmbedding(BaseModel):
    """Persisted embedding record for a single posting."""

    posting_id: int
    text_source: Literal["role_summary", "full_jd"]
    text_hash: str
    embedding: list[float]
    embedding_dim: int
    model_name: str
    embedded_at: str  # ISO-8601 UTC


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def cosine(
    v1: "np.ndarray | list[float]",
    v2: "np.ndarray | list[float]",
) -> float:
    """Return the cosine similarity between two float vectors.

    Returns 0.0 when either vector is the zero vector.
    """
    a = np.asarray(v1, dtype=np.float32)
    b = np.asarray(v2, dtype=np.float32)
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _select_text_source(
    row: sqlite3.Row | dict,
) -> tuple[str, Literal["role_summary", "full_jd"]] | None:
    """Return (text, source_label) for embedding, preferring role_summary.

    Returns None when both fields are empty — caller logs WARNING and skips.
    """
    role_summary = (row["role_summary"] or "").strip()
    full_jd = (row["full_jd"] or "").strip()
    if role_summary:
        return role_summary, "role_summary"
    if full_jd:
        return full_jd, "full_jd"
    return None


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pack_embedding(vec: np.ndarray) -> bytes:
    """Pack float32 numpy array into raw bytes for BLOB storage."""
    return vec.astype(np.float32).tobytes()


def _unpack_embedding(blob: bytes) -> np.ndarray:
    """Unpack raw BLOB bytes back into a float32 numpy array."""
    return np.frombuffer(blob, dtype=np.float32)


def _fetch_posting_row(
    posting_id: int,
    db_path: Path,
) -> dict | None:
    """Fetch posting fields needed for embedding from postings table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, role_summary, full_jd FROM postings WHERE id = ?",
            (posting_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _cache_lookup(
    posting_id: int,
    text_hash: str,
    model_name: str,
    db_path: Path,
) -> PostingEmbedding | None:
    """Return cached PostingEmbedding if posting_id + text_hash + model_name match."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT text_source, text_hash, embedding, embedding_dim, model_name, embedded_at
            FROM posting_embeddings
            WHERE posting_id = ? AND text_hash = ? AND model_name = ?
            """,
            (str(posting_id), text_hash, model_name),
        ).fetchone()
        if row is None:
            return None
        vec = _unpack_embedding(row[2])
        return PostingEmbedding(
            posting_id=posting_id,
            text_source=row[0],
            text_hash=row[1],
            embedding=vec.tolist(),
            embedding_dim=row[3],
            model_name=row[4],
            embedded_at=row[5],
        )
    finally:
        conn.close()


def _write_embedding_row(
    posting_id: int,
    text_source: str,
    text_hash: str,
    vec: np.ndarray,
    model_name: str,
    embedded_at: str,
    db_path: Path,
) -> None:
    blob = _pack_embedding(vec)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            INSERT OR REPLACE INTO posting_embeddings
                (posting_id, user_id, text_source, text_hash, embedding,
                 embedding_dim, model_name, embedded_at)
            VALUES (?, 'default', ?, ?, ?, ?, ?, ?)
            """,
            (
                str(posting_id),
                text_source,
                text_hash,
                blob,
                len(vec),
                model_name,
                embedded_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _write_ledger_cache_hit(
    posting_id: int | None,
    model_name: str,
    db_path: Path,
) -> None:
    """Write a zero-cost cache_hit ledger row."""
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO llm_call_ledger
                    (provider, model_name, call_kind, input_tokens, output_tokens,
                     cost_usd, latency_ms, posting_id, called_at, status)
                VALUES ('openai', ?, 'embedding', 0, NULL, 0.0, 0, ?, ?, 'cache_hit')
                """,
                (
                    model_name,
                    str(posting_id) if posting_id is not None else None,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("embed: ledger cache_hit write failed — %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def embed_posting(
    posting_id: int,
    db_path: Path | None = None,
    provider: EmbeddingProvider | None = None,
) -> PostingEmbedding:
    """Embed a single posting and return the PostingEmbedding record.

    Raises:
        ValueError: When the posting is not found in the DB.
        LLMProviderError: When the embedding provider fails.
    """
    resolved_db = db_path or _DEFAULT_DB_PATH

    row = _fetch_posting_row(posting_id, resolved_db)
    if row is None:
        raise ValueError(f"Posting {posting_id} not found in DB")

    result = _select_text_source(row)
    if result is None:
        logger.warning(
            "embed: posting %d has empty role_summary AND full_jd — skipping",
            posting_id,
        )
        raise ValueError(
            f"Posting {posting_id}: both role_summary and full_jd are empty — cannot embed"
        )

    text, source_label = result
    emb_provider = provider or _get_default_provider(resolved_db)
    model_name = getattr(emb_provider, "model", _EMBEDDING_MODEL)
    text_hash = _sha256(text)

    # Cache lookup
    cached = _cache_lookup(posting_id, text_hash, model_name, resolved_db)
    if cached is not None:
        logger.debug("embed: cache hit for posting %d (hash=%s)", posting_id, text_hash[:12])
        _write_ledger_cache_hit(posting_id, model_name, resolved_db)
        return cached

    # Provider call
    vectors, metadata = emb_provider.embed([text])
    vec = np.array(vectors[0], dtype=np.float32)
    embedded_at = datetime.now(timezone.utc).isoformat()

    _write_embedding_row(
        posting_id=posting_id,
        text_source=source_label,
        text_hash=text_hash,
        vec=vec,
        model_name=model_name,
        embedded_at=embedded_at,
        db_path=resolved_db,
    )

    logger.info(
        "embed: posting %d embedded via %s | dim=%d | source=%s | cost=$%.6f",
        posting_id,
        model_name,
        len(vec),
        source_label,
        metadata.cost_usd,
    )

    return PostingEmbedding(
        posting_id=posting_id,
        text_source=source_label,
        text_hash=text_hash,
        embedding=vec.tolist(),
        embedding_dim=len(vec),
        model_name=model_name,
        embedded_at=embedded_at,
    )


def embed_postings_batch(
    posting_ids: list[int],
    db_path: Path | None = None,
    provider: EmbeddingProvider | None = None,
) -> list[PostingEmbedding]:
    """Embed a batch of postings with cross-posting text_hash dedup.

    Postings sharing the same text_hash within this batch are sent in a single
    provider call; all rows reference the same vector. Already-cached postings
    produce a cache_hit ledger row and incur no API cost.

    Returns a list of PostingEmbedding in the same order as posting_ids.
    Postings with empty text are skipped (logged at WARNING) and absent from
    the result list.
    """
    resolved_db = db_path or _DEFAULT_DB_PATH
    emb_provider = provider or _get_default_provider(resolved_db)
    model_name = getattr(emb_provider, "model", _EMBEDDING_MODEL)

    # --- Step 1: fetch all rows and select text sources ---
    rows: dict[int, dict] = {}
    for pid in posting_ids:
        row = _fetch_posting_row(pid, resolved_db)
        if row is not None:
            rows[pid] = row

    # --- Step 2: classify each posting as cached / needs-embedding / skip ---
    results: list[PostingEmbedding] = []
    needs_embedding: list[tuple[int, str, Literal["role_summary", "full_jd"], str]] = []
    # (posting_id, text, source_label, text_hash)

    for pid in posting_ids:
        if pid not in rows:
            logger.warning("embed_batch: posting %d not found in DB — skipping", pid)
            continue

        row = rows[pid]
        result = _select_text_source(row)
        if result is None:
            logger.warning(
                "embed_batch: posting %d has empty role_summary AND full_jd — skipping",
                pid,
            )
            continue

        text, source_label = result
        text_hash = _sha256(text)
        cached = _cache_lookup(pid, text_hash, model_name, resolved_db)
        if cached is not None:
            logger.debug("embed_batch: cache hit for posting %d", pid)
            _write_ledger_cache_hit(pid, model_name, resolved_db)
            results.append(cached)
        else:
            needs_embedding.append((pid, text, source_label, text_hash))

    if not needs_embedding:
        logger.info("embed_batch: all %d postings were cache hits", len(results))
        return results

    # --- Step 3: batch-dedup by text_hash → one provider call per unique text ---
    # Map text_hash → (text, source_label, [posting_ids that share this hash])
    hash_to_group: dict[str, tuple[str, str, list[int]]] = {}
    for pid, text, source_label, text_hash in needs_embedding:
        if text_hash not in hash_to_group:
            hash_to_group[text_hash] = (text, source_label, [])
        hash_to_group[text_hash][2].append(pid)

    unique_texts = [v[0] for v in hash_to_group.values()]
    hash_order = list(hash_to_group.keys())

    logger.info(
        "embed_batch: %d postings need embedding → %d unique texts (batch dedup saved %d calls)",
        len(needs_embedding),
        len(unique_texts),
        len(needs_embedding) - len(unique_texts),
    )

    t0 = perf_counter()
    vectors, metadata = emb_provider.embed(unique_texts)
    latency_ms = int((perf_counter() - t0) * 1000)

    embedded_at = datetime.now(timezone.utc).isoformat()

    # --- Step 4: write all posting_embeddings rows (shared vector for same text_hash) ---
    for i, text_hash in enumerate(hash_order):
        text, source_label, pids_for_hash = hash_to_group[text_hash]
        vec = np.array(vectors[i], dtype=np.float32)
        for pid in pids_for_hash:
            _write_embedding_row(
                posting_id=pid,
                text_source=source_label,
                text_hash=text_hash,
                vec=vec,
                model_name=model_name,
                embedded_at=embedded_at,
                db_path=resolved_db,
            )
            results.append(
                PostingEmbedding(
                    posting_id=pid,
                    text_source=source_label,
                    text_hash=text_hash,
                    embedding=vec.tolist(),
                    embedding_dim=len(vec),
                    model_name=model_name,
                    embedded_at=embedded_at,
                )
            )

    logger.info(
        "embed_batch: %d postings embedded (%d unique calls) | cost=$%.6f | %dms",
        len(needs_embedding),
        len(unique_texts),
        metadata.cost_usd,
        latency_ms,
    )

    return results


# ---------------------------------------------------------------------------
# Internal provider factory
# ---------------------------------------------------------------------------


def _get_default_provider(db_path: Path) -> EmbeddingProvider:
    from jd_matcher.llm.providers.factory import make_embedder

    return make_embedder(db_path=db_path)


# ---------------------------------------------------------------------------
# CLI entry point — python -m jd_matcher.llm.embed --posting-id <id>
# ---------------------------------------------------------------------------


def _main() -> None:
    import os

    import logging

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path.cwd() / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    parser = argparse.ArgumentParser(description="C20 — embed a posting's role_summary")
    parser.add_argument("--posting-id", type=int, required=True)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=_DEFAULT_DB_PATH,
        help="Path to SQLite DB (default: ~/.jd-matcher/jd-matcher.db)",
    )
    args = parser.parse_args()

    result = embed_posting(posting_id=args.posting_id, db_path=args.db_path)
    print(f"posting_id   : {result.posting_id}")
    print(f"text_source  : {result.text_source}")
    print(f"model_name   : {result.model_name}")
    print(f"embedding_dim: {result.embedding_dim}")
    print(f"text_hash    : {result.text_hash[:16]}…")
    print(f"embedded_at  : {result.embedded_at}")
    print(f"vector[0:4]  : {result.embedding[:4]}")


if __name__ == "__main__":
    _main()
