"""AC #2 + #8 — OpenAIExtractor implementation and mock-at-boundary tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_completion(content: str, input_tokens: int = 100, output_tokens: int = 20):
    mock = MagicMock()
    mock.choices[0].message.content = content
    mock.usage.prompt_tokens = input_tokens
    mock.usage.completion_tokens = output_tokens
    return mock


def _make_extractor(db_path=None, model="gpt-4o-mini"):
    from jd_matcher.llm.providers.openai_extractor import OpenAIExtractor

    return OpenAIExtractor(model=model, db_path=db_path, api_key="test-key")


@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")
def test_extract_returns_raw_content(mock_openai_class):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_completion(
        '{"role": "Data Scientist"}'
    )
    mock_openai_class.return_value = mock_client

    extractor = _make_extractor(db_path=None)
    raw, meta = extractor.extract("hello", "be helpful", {"type": "json_object"})

    assert raw == '{"role": "Data Scientist"}'


@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")
def test_extract_returns_metadata_tokens(mock_openai_class):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_completion(
        '{"x": 1}', input_tokens=100, output_tokens=20
    )
    mock_openai_class.return_value = mock_client

    extractor = _make_extractor(db_path=None)
    _, meta = extractor.extract("prompt", "system", {"type": "json_object"})

    assert meta.input_tokens == 100
    assert meta.output_tokens == 20


@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")
def test_extract_metadata_cost_nonzero(mock_openai_class):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_completion(
        "{}", input_tokens=1000, output_tokens=200
    )
    mock_openai_class.return_value = mock_client

    extractor = _make_extractor(db_path=None)
    _, meta = extractor.extract("prompt", "system", {"type": "json_object"})

    assert meta.cost_usd > 0
    assert abs(meta.cost_usd - 0.00027) < 1e-9


@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")
def test_extract_metadata_latency_ms_positive(mock_openai_class):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_completion("{}")
    mock_openai_class.return_value = mock_client

    extractor = _make_extractor(db_path=None)
    _, meta = extractor.extract("prompt", "system", {"type": "json_object"})

    assert meta.latency_ms >= 0


@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")
def test_extract_rate_limit_raises_our_error(mock_openai_class):
    """openai.RateLimitError is translated to providers.base.RateLimitError."""
    import openai as openai_sdk

    from jd_matcher.llm.providers.base import RateLimitError

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = openai_sdk.RateLimitError(
        message="rate limit", response=MagicMock(), body={}
    )
    mock_openai_class.return_value = mock_client

    extractor = _make_extractor(db_path=None)
    with pytest.raises(RateLimitError):
        extractor.extract("prompt", "system", {"type": "json_object"})


@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")
def test_extract_connection_error_raises_provider_unavailable(mock_openai_class):
    """openai.APIConnectionError is translated to ProviderUnavailableError."""
    import openai as openai_sdk

    from jd_matcher.llm.providers.base import ProviderUnavailableError

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = openai_sdk.APIConnectionError(
        request=MagicMock()
    )
    mock_openai_class.return_value = mock_client

    extractor = _make_extractor(db_path=None)
    with pytest.raises(ProviderUnavailableError):
        extractor.extract("prompt", "system", {"type": "json_object"})


@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")
def test_extract_generic_openai_error_raises_llm_provider_error(mock_openai_class):
    import openai as openai_sdk

    from jd_matcher.llm.providers.base import LLMProviderError

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = openai_sdk.BadRequestError(
        message="bad", response=MagicMock(), body={}
    )
    mock_openai_class.return_value = mock_client

    extractor = _make_extractor(db_path=None)
    with pytest.raises(LLMProviderError):
        extractor.extract("prompt", "system", {"type": "json_object"})


@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")
def test_openai_extractor_model_default(mock_openai_class):
    from jd_matcher.llm.providers.openai_extractor import OpenAIExtractor

    extractor = OpenAIExtractor(db_path=None, api_key="test-key")
    assert extractor.model == "gpt-4o-mini"
