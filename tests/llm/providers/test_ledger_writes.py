"""AC #7 — llm_call_ledger row written per call (real tmp SQLite)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jd_matcher.db.init_db import init_db


def _mock_completion(content: str = "{}", input_tokens: int = 100, output_tokens: int = 20):
    mock = MagicMock()
    mock.choices[0].message.content = content
    mock.usage.prompt_tokens = input_tokens
    mock.usage.completion_tokens = output_tokens
    return mock


def _mock_embedding_response(vectors=None, total_tokens: int = 50):
    if vectors is None:
        vectors = [[0.1, 0.2]]
    response = MagicMock()
    response.data = [MagicMock(embedding=v) for v in vectors]
    response.usage.total_tokens = total_tokens
    return response


def _query_ledger(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM llm_call_ledger ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")
def test_extract_success_writes_ledger_row(mock_openai_class, tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_completion(
        '{"role":"DS"}', input_tokens=200, output_tokens=30
    )
    mock_openai_class.return_value = mock_client

    from jd_matcher.llm.providers.openai_extractor import OpenAIExtractor

    extractor = OpenAIExtractor(model="gpt-4o-mini", db_path=db_path, api_key="test-key")
    extractor.extract("prompt", "system", {"type": "json_object"})

    rows = _query_ledger(db_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["provider"] == "openai"
    assert row["model_name"] == "gpt-4o-mini"
    assert row["call_kind"] == "extraction"
    assert row["input_tokens"] == 200
    assert row["output_tokens"] == 30
    assert row["cost_usd"] > 0
    assert row["latency_ms"] >= 0
    assert row["status"] == "success"


@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")
def test_extract_failure_writes_ledger_row_with_failure_status(mock_openai_class, tmp_path):
    import openai as openai_sdk

    from jd_matcher.llm.providers.base import RateLimitError

    db_path = tmp_path / "test.db"
    init_db(db_path)

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = openai_sdk.RateLimitError(
        message="rate limit", response=MagicMock(), body={}
    )
    mock_openai_class.return_value = mock_client

    from jd_matcher.llm.providers.openai_extractor import OpenAIExtractor

    extractor = OpenAIExtractor(model="gpt-4o-mini", db_path=db_path, api_key="test-key")
    with pytest.raises(RateLimitError):
        extractor.extract("prompt", "system", {"type": "json_object"})

    rows = _query_ledger(db_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "failure"
    assert rows[0]["cost_usd"] == 0.0


@patch("jd_matcher.llm.providers.openai_embedding.openai.OpenAI")
def test_embed_success_writes_ledger_row(mock_openai_class, tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = _mock_embedding_response(
        [[0.1, 0.2]], total_tokens=80
    )
    mock_openai_class.return_value = mock_client

    from jd_matcher.llm.providers.openai_embedding import OpenAIEmbedding

    embedder = OpenAIEmbedding(
        model="text-embedding-3-small", db_path=db_path, api_key="test-key"
    )
    embedder.embed(["text one"])

    rows = _query_ledger(db_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["provider"] == "openai"
    assert row["model_name"] == "text-embedding-3-small"
    assert row["call_kind"] == "embedding"
    assert row["input_tokens"] == 80
    assert row["output_tokens"] is None
    assert row["cost_usd"] > 0
    assert row["status"] == "success"


@patch("jd_matcher.llm.providers.openai_embedding.openai.OpenAI")
def test_embed_failure_writes_ledger_row_with_failure_status(mock_openai_class, tmp_path):
    import openai as openai_sdk

    from jd_matcher.llm.providers.base import RateLimitError

    db_path = tmp_path / "test.db"
    init_db(db_path)

    mock_client = MagicMock()
    mock_client.embeddings.create.side_effect = openai_sdk.RateLimitError(
        message="rate limit", response=MagicMock(), body={}
    )
    mock_openai_class.return_value = mock_client

    from jd_matcher.llm.providers.openai_embedding import OpenAIEmbedding

    embedder = OpenAIEmbedding(
        model="text-embedding-3-small", db_path=db_path, api_key="test-key"
    )
    with pytest.raises(RateLimitError):
        embedder.embed(["text"])

    rows = _query_ledger(db_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "failure"


@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")
def test_extract_no_db_path_skips_ledger(mock_openai_class, tmp_path):
    """db_path=None means no ledger writes — should not error."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_completion("{}")
    mock_openai_class.return_value = mock_client

    from jd_matcher.llm.providers.openai_extractor import OpenAIExtractor

    extractor = OpenAIExtractor(model="gpt-4o-mini", db_path=None, api_key="test-key")
    raw, meta = extractor.extract("prompt", "system", {"type": "json_object"})

    # No assertion on DB — just assert the call succeeded without exception
    assert raw == "{}"
