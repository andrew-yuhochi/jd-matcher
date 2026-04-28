"""Base Protocols, metadata dataclasses, and custom exceptions for C28.

C18 and C20 import only from this module (or from jd_matcher.llm) —
they never reference provider-specific modules directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Metadata containers returned alongside provider outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractionMetadata:
    """Telemetry returned alongside every LLMExtractor.extract() call."""

    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float


@dataclass(frozen=True)
class EmbeddingMetadata:
    """Telemetry returned alongside every EmbeddingProvider.embed() call."""

    input_tokens: int
    latency_ms: int
    cost_usd: float


# ---------------------------------------------------------------------------
# Custom exceptions — provider-specific errors translated to these types
# so C18/C20 never need to import openai or ollama error classes.
# ---------------------------------------------------------------------------


class LLMProviderError(Exception):
    """Base class for all provider errors surfaced through the abstraction."""


class RateLimitError(LLMProviderError):
    """Provider returned a 429 / rate-limit response."""


class ProviderUnavailableError(LLMProviderError):
    """Provider is unreachable (connection refused, network failure, etc.)."""


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMExtractor(Protocol):
    """Interface for LLM text extraction providers."""

    def extract(
        self,
        prompt: str,
        system: str,
        response_format: dict,
    ) -> tuple[str, ExtractionMetadata]:
        """Run an extraction call and return the raw JSON string + telemetry.

        Args:
            prompt: User-turn message sent to the model.
            system: System prompt defining the extraction task.
            response_format: OpenAI-compatible response format dict, e.g.
                ``{"type": "json_object"}`` or
                ``{"type": "json_schema", "json_schema": {...}}``.

        Returns:
            A ``(raw_json_str, ExtractionMetadata)`` 2-tuple.

        Raises:
            RateLimitError: Provider rejected the request due to rate limits.
            ProviderUnavailableError: Provider is unreachable.
            LLMProviderError: Any other provider-level error.
        """
        ...

    @classmethod
    def from_config(
        cls,
        provider: str | None = None,
        model: str | None = None,
        db_path: object = None,
    ) -> "LLMExtractor":
        """Construct the configured implementation.

        Reading from ``config/llm.yaml`` (optional file — missing falls back
        to cloud OpenAI defaults).  ``provider`` and ``model`` override the
        config when supplied.
        """
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Interface for text embedding providers."""

    def embed(
        self,
        texts: list[str],
    ) -> tuple[list[list[float]], EmbeddingMetadata]:
        """Embed a batch of texts and return vectors + telemetry.

        Args:
            texts: One or more strings to embed in a single provider call.

        Returns:
            A ``(list_of_vectors, EmbeddingMetadata)`` 2-tuple where
            ``list_of_vectors[i]`` corresponds to ``texts[i]``.

        Raises:
            RateLimitError: Provider rejected the request due to rate limits.
            ProviderUnavailableError: Provider is unreachable.
            LLMProviderError: Any other provider-level error.
        """
        ...

    @classmethod
    def from_config(
        cls,
        provider: str | None = None,
        model: str | None = None,
        db_path: object = None,
    ) -> "EmbeddingProvider":
        """Construct the configured implementation."""
        ...
