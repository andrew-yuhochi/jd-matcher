"""Factory functions for constructing LLM provider instances from config.

C18 and C20 call ``make_extractor()`` / ``make_embedder()`` (or use
``LLMExtractor.from_config()`` / ``EmbeddingProvider.from_config()`` which
delegate here).  Neither the callers nor this module import openai or ollama
— provider-specific imports are confined to the leaf implementation modules.
"""

from __future__ import annotations

import logging
from pathlib import Path

from jd_matcher.llm.providers.base import EmbeddingProvider, LLMExtractor

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"

_EXTRACTOR_REGISTRY: dict[str, type] = {}
_EMBEDDER_REGISTRY: dict[str, type] = {}


def _extractor_registry() -> dict[str, type]:
    if not _EXTRACTOR_REGISTRY:
        from jd_matcher.llm.providers.ollama_extractor import OllamaExtractor
        from jd_matcher.llm.providers.openai_extractor import OpenAIExtractor

        _EXTRACTOR_REGISTRY["openai"] = OpenAIExtractor
        _EXTRACTOR_REGISTRY["ollama"] = OllamaExtractor
    return _EXTRACTOR_REGISTRY


def _embedder_registry() -> dict[str, type]:
    if not _EMBEDDER_REGISTRY:
        from jd_matcher.llm.providers.ollama_embedding import OllamaEmbedding
        from jd_matcher.llm.providers.openai_embedding import OpenAIEmbedding

        _EMBEDDER_REGISTRY["openai"] = OpenAIEmbedding
        _EMBEDDER_REGISTRY["ollama"] = OllamaEmbedding
    return _EMBEDDER_REGISTRY


def make_extractor(
    provider: str | None = None,
    model: str | None = None,
    db_path: Path | None = _DEFAULT_DB_PATH,
) -> LLMExtractor:
    """Return the configured LLMExtractor implementation.

    Args:
        provider: Provider name (``'openai'`` or ``'ollama'``).  Reads from
                  ``config/llm.yaml`` when ``None``.
        model: Model name override.  Reads from ``config/llm.yaml`` when ``None``.
        db_path: SQLite DB path for ledger writes.  Pass ``None`` to disable.

    Returns:
        A concrete ``LLMExtractor`` instance.

    Raises:
        ValueError: When ``provider`` is not a known name.
        NotImplementedError: When the stub provider (Ollama) is requested.
    """
    from jd_matcher.llm.providers.config import load_llm_config

    cfg = load_llm_config()
    resolved_provider = provider if provider is not None else cfg.extraction.provider
    resolved_model = model if model is not None else cfg.extraction.model

    registry = _extractor_registry()
    cls = registry.get(resolved_provider)
    if cls is None:
        raise ValueError(
            f"Unknown extraction provider '{resolved_provider}'. "
            f"Available providers: {sorted(registry)}"
        )

    logger.debug("make_extractor: provider=%s model=%s", resolved_provider, resolved_model)

    # Ollama stub raises NotImplementedError in __init__; let it propagate
    return cls(model=resolved_model, db_path=db_path)  # type: ignore[call-arg]


def make_embedder(
    provider: str | None = None,
    model: str | None = None,
    db_path: Path | None = _DEFAULT_DB_PATH,
) -> EmbeddingProvider:
    """Return the configured EmbeddingProvider implementation.

    Args:
        provider: Provider name (``'openai'`` or ``'ollama'``).  Reads from
                  ``config/llm.yaml`` when ``None``.
        model: Model name override.  Reads from config when ``None``.
        db_path: SQLite DB path for ledger writes.  Pass ``None`` to disable.

    Returns:
        A concrete ``EmbeddingProvider`` instance.

    Raises:
        ValueError: When ``provider`` is not a known name.
        NotImplementedError: When the stub provider (Ollama) is requested.
    """
    from jd_matcher.llm.providers.config import load_llm_config

    cfg = load_llm_config()
    resolved_provider = provider if provider is not None else cfg.embedding.provider
    resolved_model = model if model is not None else cfg.embedding.model

    registry = _embedder_registry()
    cls = registry.get(resolved_provider)
    if cls is None:
        raise ValueError(
            f"Unknown embedding provider '{resolved_provider}'. "
            f"Available providers: {sorted(registry)}"
        )

    logger.debug("make_embedder: provider=%s model=%s", resolved_provider, resolved_model)

    return cls(model=resolved_model, db_path=db_path)  # type: ignore[call-arg]
