"""AC #1 — Protocol conformance: both impls satisfy LLMExtractor and EmbeddingProvider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jd_matcher.llm.providers.base import EmbeddingProvider, LLMExtractor


def _make_extractor(tmp_path):
    with patch("openai.OpenAI"):
        from jd_matcher.llm.providers.openai_extractor import OpenAIExtractor

        return OpenAIExtractor(model="gpt-4o-mini", db_path=None, api_key="test-key")


def _make_embedder(tmp_path):
    with patch("openai.OpenAI"):
        from jd_matcher.llm.providers.openai_embedding import OpenAIEmbedding

        return OpenAIEmbedding(
            model="text-embedding-3-small", db_path=None, api_key="test-key"
        )


def test_openai_extractor_satisfies_protocol(tmp_path):
    """OpenAIExtractor is a structural subtype of LLMExtractor."""
    instance = _make_extractor(tmp_path)
    assert isinstance(instance, LLMExtractor)


def test_openai_embedding_satisfies_protocol(tmp_path):
    """OpenAIEmbedding is a structural subtype of EmbeddingProvider."""
    instance = _make_embedder(tmp_path)
    assert isinstance(instance, EmbeddingProvider)


def test_llm_extractor_protocol_has_extract_method():
    """Protocol declares extract() — checked via hasattr on a concrete impl."""
    from jd_matcher.llm.providers.openai_extractor import OpenAIExtractor

    assert hasattr(OpenAIExtractor, "extract")


def test_embedding_provider_protocol_has_embed_method():
    """Protocol declares embed() — checked via hasattr on a concrete impl."""
    from jd_matcher.llm.providers.openai_embedding import OpenAIEmbedding

    assert hasattr(OpenAIEmbedding, "embed")
