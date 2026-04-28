"""AC #3 + #8 — OpenAIEmbedding implementation and mock-at-boundary tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_embedding_response(vectors: list[list[float]], total_tokens: int = 50):
    response = MagicMock()
    response.data = [MagicMock(embedding=v) for v in vectors]
    response.usage.total_tokens = total_tokens
    return response


def _make_embedder(db_path=None, model="text-embedding-3-small"):
    from jd_matcher.llm.providers.openai_embedding import OpenAIEmbedding

    return OpenAIEmbedding(model=model, db_path=db_path, api_key="test-key")


@patch("jd_matcher.llm.providers.openai_embedding.openai.OpenAI")
def test_embed_returns_vectors(mock_openai_class):
    vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = _mock_embedding_response(vectors)
    mock_openai_class.return_value = mock_client

    embedder = _make_embedder(db_path=None)
    result_vectors, meta = embedder.embed(["text one", "text two"])

    assert result_vectors == vectors
    assert len(result_vectors) == 2


@patch("jd_matcher.llm.providers.openai_embedding.openai.OpenAI")
def test_embed_returns_metadata_tokens(mock_openai_class):
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = _mock_embedding_response(
        [[0.1]], total_tokens=123
    )
    mock_openai_class.return_value = mock_client

    embedder = _make_embedder(db_path=None)
    _, meta = embedder.embed(["hello"])

    assert meta.input_tokens == 123


@patch("jd_matcher.llm.providers.openai_embedding.openai.OpenAI")
def test_embed_cost_nonzero(mock_openai_class):
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = _mock_embedding_response(
        [[0.1]], total_tokens=1000
    )
    mock_openai_class.return_value = mock_client

    embedder = _make_embedder(db_path=None)
    _, meta = embedder.embed(["text"])

    assert meta.cost_usd > 0
    assert abs(meta.cost_usd - 0.00002) < 1e-9


@patch("jd_matcher.llm.providers.openai_embedding.openai.OpenAI")
def test_embed_rate_limit_raises_our_error(mock_openai_class):
    import openai as openai_sdk

    from jd_matcher.llm.providers.base import RateLimitError

    mock_client = MagicMock()
    mock_client.embeddings.create.side_effect = openai_sdk.RateLimitError(
        message="rate limit", response=MagicMock(), body={}
    )
    mock_openai_class.return_value = mock_client

    embedder = _make_embedder(db_path=None)
    with pytest.raises(RateLimitError):
        embedder.embed(["text"])


@patch("jd_matcher.llm.providers.openai_embedding.openai.OpenAI")
def test_embed_connection_error_raises_provider_unavailable(mock_openai_class):
    import openai as openai_sdk

    from jd_matcher.llm.providers.base import ProviderUnavailableError

    mock_client = MagicMock()
    mock_client.embeddings.create.side_effect = openai_sdk.APIConnectionError(
        request=MagicMock()
    )
    mock_openai_class.return_value = mock_client

    embedder = _make_embedder(db_path=None)
    with pytest.raises(ProviderUnavailableError):
        embedder.embed(["text"])


@patch("jd_matcher.llm.providers.openai_embedding.openai.OpenAI")
def test_openai_embedding_model_default(mock_openai_class):
    from jd_matcher.llm.providers.openai_embedding import OpenAIEmbedding

    embedder = OpenAIEmbedding(db_path=None, api_key="test-key")
    assert embedder.model == "text-embedding-3-small"
