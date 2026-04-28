"""OpenAI-backed EmbeddingProvider implementation (C28 cloud default).

C20 imports only from jd_matcher.llm — never from openai directly.
All OpenAI SDK usage is confined to this module.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import openai

from jd_matcher.llm.providers.base import (
    EmbeddingMetadata,
    LLMProviderError,
    ProviderUnavailableError,
    RateLimitError,
)
from jd_matcher.llm.providers.pricing import compute_cost

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"


class OpenAIEmbedding:
    """Text embedding using the OpenAI embeddings API.

    Writes one ``llm_call_ledger`` row per call (a batch of N texts = 1 row).
    Pass ``db_path=None`` to skip ledger writes (useful in unit tests).
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        db_path: Path | None = _DEFAULT_DB_PATH,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.db_path = db_path
        self._api_key = api_key
        self._client: openai.OpenAI | None = None

    # ------------------------------------------------------------------
    # Protocol classmethod entry point
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        provider: str | None = None,
        model: str | None = None,
        db_path: object = _DEFAULT_DB_PATH,
    ) -> "OpenAIEmbedding":
        from jd_matcher.llm.providers.config import load_llm_config

        cfg = load_llm_config()
        resolved_model = model if model is not None else cfg.embedding.model
        resolved_db = db_path if db_path is not None else _DEFAULT_DB_PATH
        return cls(model=resolved_model, db_path=resolved_db)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> openai.OpenAI:
        if self._client is None:
            from jd_matcher.llm import get_openai_key

            key = self._api_key or get_openai_key()
            self._client = openai.OpenAI(api_key=key)
        return self._client

    def _write_ledger(
        self,
        *,
        status: str,
        input_tokens: int,
        cost_usd: float,
        latency_ms: int,
    ) -> None:
        if self.db_path is None:
            return
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("PRAGMA foreign_keys = ON;")
                conn.execute(
                    """
                    INSERT INTO llm_call_ledger
                        (provider, model_name, call_kind,
                         input_tokens, output_tokens, cost_usd,
                         latency_ms, posting_id, called_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "openai",
                        self.model,
                        "embedding",
                        input_tokens,
                        None,  # embedding has no output tokens
                        cost_usd,
                        latency_ms,
                        None,  # batch call — no single posting_id
                        datetime.now(timezone.utc).isoformat(),
                        status,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("openai_embedding: ledger write failed — %s", exc)

    # ------------------------------------------------------------------
    # Protocol method
    # ------------------------------------------------------------------

    def embed(
        self,
        texts: list[str],
    ) -> tuple[list[list[float]], EmbeddingMetadata]:
        """Embed a batch of texts and return (vectors, EmbeddingMetadata).

        Raises:
            RateLimitError: On HTTP 429.
            ProviderUnavailableError: On connection errors.
            LLMProviderError: On any other OpenAI SDK error.
        """
        client = self._get_client()
        t0 = perf_counter()
        input_tokens = 0
        cost_usd = 0.0

        try:
            response = client.embeddings.create(model=self.model, input=texts)
        except openai.RateLimitError as exc:
            latency_ms = int((perf_counter() - t0) * 1000)
            self._write_ledger(
                status="failure",
                input_tokens=0,
                cost_usd=0.0,
                latency_ms=latency_ms,
            )
            raise RateLimitError(str(exc)) from exc
        except openai.APIConnectionError as exc:
            latency_ms = int((perf_counter() - t0) * 1000)
            self._write_ledger(
                status="failure",
                input_tokens=0,
                cost_usd=0.0,
                latency_ms=latency_ms,
            )
            raise ProviderUnavailableError(str(exc)) from exc
        except openai.OpenAIError as exc:
            latency_ms = int((perf_counter() - t0) * 1000)
            self._write_ledger(
                status="failure",
                input_tokens=0,
                cost_usd=0.0,
                latency_ms=latency_ms,
            )
            raise LLMProviderError(str(exc)) from exc

        latency_ms = int((perf_counter() - t0) * 1000)

        if response.usage:
            input_tokens = response.usage.total_tokens

        cost_usd = compute_cost(self.model, input_tokens)
        vectors = [item.embedding for item in response.data]

        self._write_ledger(
            status="success",
            input_tokens=input_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

        metadata = EmbeddingMetadata(
            input_tokens=input_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )
        logger.debug(
            "openai_embedding: embedded %d text(s) via %s | tokens=%d | cost=$%.6f | %dms",
            len(texts),
            self.model,
            input_tokens,
            cost_usd,
            latency_ms,
        )
        return vectors, metadata
