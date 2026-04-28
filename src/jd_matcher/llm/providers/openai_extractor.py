"""OpenAI-backed LLMExtractor implementation (C28 cloud default).

C18 imports only from jd_matcher.llm — never from openai directly.
All OpenAI SDK usage is confined to this module.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

import openai

from jd_matcher.llm.providers.base import (
    ExtractionMetadata,
    LLMProviderError,
    ProviderUnavailableError,
    RateLimitError,
)
from jd_matcher.llm.providers.pricing import compute_cost

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"


class OpenAIExtractor:
    """LLM extraction using the OpenAI chat completions API.

    Writes one ``llm_call_ledger`` row per call (success or failure).
    Pass ``db_path=None`` to skip ledger writes (useful in unit tests that
    want to assert on the return value only).
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        db_path: Path | None = _DEFAULT_DB_PATH,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.db_path = db_path
        # Lazily resolved; callers may inject a pre-built client for testing
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
    ) -> "OpenAIExtractor":
        """Build an instance from config defaults.

        ``provider`` is accepted but ignored here — factory.py routes to the
        correct class before calling from_config().
        """
        from jd_matcher.llm.providers.config import load_llm_config

        cfg = load_llm_config()
        resolved_model = model if model is not None else cfg.extraction.model
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
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        posting_id: str | None = None,
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
                        "extraction",
                        input_tokens,
                        output_tokens,
                        cost_usd,
                        latency_ms,
                        posting_id,
                        datetime.now(timezone.utc).isoformat(),
                        status,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            # Ledger failure must never crash the extraction path
            logger.warning("openai_extractor: ledger write failed — %s", exc)

    # ------------------------------------------------------------------
    # Protocol method
    # ------------------------------------------------------------------

    def extract(
        self,
        prompt: str,
        system: str,
        response_format: dict,
    ) -> tuple[str, ExtractionMetadata]:
        """Call GPT-4o-mini and return (raw_json_str, ExtractionMetadata).

        Raises:
            RateLimitError: On HTTP 429.
            ProviderUnavailableError: On connection errors.
            LLMProviderError: On any other OpenAI SDK error.
        """
        client = self._get_client()
        t0 = perf_counter()
        input_tokens = output_tokens = 0
        cost_usd = 0.0

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format=response_format,
                temperature=0,
            )
        except openai.RateLimitError as exc:
            latency_ms = int((perf_counter() - t0) * 1000)
            self._write_ledger(
                status="failure",
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=latency_ms,
            )
            raise RateLimitError(str(exc)) from exc
        except openai.APIConnectionError as exc:
            latency_ms = int((perf_counter() - t0) * 1000)
            self._write_ledger(
                status="failure",
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=latency_ms,
            )
            raise ProviderUnavailableError(str(exc)) from exc
        except openai.OpenAIError as exc:
            latency_ms = int((perf_counter() - t0) * 1000)
            self._write_ledger(
                status="failure",
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=latency_ms,
            )
            raise LLMProviderError(str(exc)) from exc

        latency_ms = int((perf_counter() - t0) * 1000)

        if response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

        cost_usd = compute_cost(self.model, input_tokens, output_tokens)
        raw_content = response.choices[0].message.content or ""

        self._write_ledger(
            status="success",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

        metadata = ExtractionMetadata(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )
        logger.debug(
            "openai_extractor: extracted via %s | tokens=%d+%d | cost=$%.6f | %dms",
            self.model,
            input_tokens,
            output_tokens,
            cost_usd,
            latency_ms,
        )
        return raw_content, metadata
