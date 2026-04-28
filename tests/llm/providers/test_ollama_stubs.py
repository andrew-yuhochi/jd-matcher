"""AC #4 — Ollama stubs raise NotImplementedError with M3 message."""

from __future__ import annotations

import pytest


def test_ollama_extractor_init_raises_not_implemented():
    from jd_matcher.llm.providers.ollama_extractor import OllamaExtractor

    with pytest.raises(NotImplementedError, match="M3"):
        OllamaExtractor()


def test_ollama_extractor_from_config_raises_not_implemented():
    from jd_matcher.llm.providers.ollama_extractor import OllamaExtractor

    with pytest.raises(NotImplementedError, match="M3"):
        OllamaExtractor.from_config()


def test_ollama_embedding_init_raises_not_implemented():
    from jd_matcher.llm.providers.ollama_embedding import OllamaEmbedding

    with pytest.raises(NotImplementedError, match="M3"):
        OllamaEmbedding()


def test_ollama_embedding_from_config_raises_not_implemented():
    from jd_matcher.llm.providers.ollama_embedding import OllamaEmbedding

    with pytest.raises(NotImplementedError, match="M3"):
        OllamaEmbedding.from_config()


def test_make_extractor_ollama_raises_not_implemented():
    """factory.make_extractor('ollama') raises NotImplementedError (stub)."""
    from jd_matcher.llm.providers.factory import make_extractor

    with pytest.raises(NotImplementedError, match="M3"):
        make_extractor(provider="ollama", db_path=None)


def test_make_embedder_ollama_raises_not_implemented():
    from jd_matcher.llm.providers.factory import make_embedder

    with pytest.raises(NotImplementedError, match="M3"):
        make_embedder(provider="ollama", db_path=None)
