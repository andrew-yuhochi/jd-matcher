"""AC #5 — Factory pattern: from_config / make_extractor / make_embedder."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_make_extractor_openai_returns_openai_extractor():
    from jd_matcher.llm.providers.factory import make_extractor
    from jd_matcher.llm.providers.openai_extractor import OpenAIExtractor

    extractor = make_extractor(provider="openai", db_path=None)
    assert isinstance(extractor, OpenAIExtractor)


def test_make_embedder_openai_returns_openai_embedding():
    from jd_matcher.llm.providers.factory import make_embedder
    from jd_matcher.llm.providers.openai_embedding import OpenAIEmbedding

    embedder = make_embedder(provider="openai", db_path=None)
    assert isinstance(embedder, OpenAIEmbedding)


def test_make_extractor_unknown_provider_raises_value_error():
    from jd_matcher.llm.providers.factory import make_extractor

    with pytest.raises(ValueError, match="Unknown extraction provider"):
        make_extractor(provider="not-a-provider", db_path=None)


def test_make_embedder_unknown_provider_raises_value_error():
    from jd_matcher.llm.providers.factory import make_embedder

    with pytest.raises(ValueError, match="Unknown embedding provider"):
        make_embedder(provider="not-a-provider", db_path=None)


def test_make_extractor_uses_config_defaults_when_no_provider_given(tmp_path):
    """When provider=None, factory reads from config (default=openai)."""
    from jd_matcher.llm.providers.factory import make_extractor
    from jd_matcher.llm.providers.openai_extractor import OpenAIExtractor

    extractor = make_extractor(provider=None, db_path=None)
    assert isinstance(extractor, OpenAIExtractor)


def test_llm_extractor_from_config_returns_openai_extractor():
    """AC #5 — LLMExtractor.from_config() classmethod entry point."""
    from jd_matcher.llm import LLMExtractor
    from jd_matcher.llm.providers.openai_extractor import OpenAIExtractor

    e = LLMExtractor.from_config(db_path=None)
    assert isinstance(e, OpenAIExtractor)


def test_embedding_provider_from_config_returns_openai_embedding():
    """EmbeddingProvider.from_config() classmethod entry point."""
    from jd_matcher.llm import EmbeddingProvider
    from jd_matcher.llm.providers.openai_embedding import OpenAIEmbedding

    e = EmbeddingProvider.from_config(db_path=None)
    assert isinstance(e, OpenAIEmbedding)


def test_make_extractor_model_override():
    """model kwarg overrides the config default."""
    from jd_matcher.llm.providers.factory import make_extractor

    extractor = make_extractor(provider="openai", model="gpt-4o", db_path=None)
    assert extractor.model == "gpt-4o"
