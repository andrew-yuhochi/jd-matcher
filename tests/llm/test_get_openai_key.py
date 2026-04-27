"""Tests for get_openai_key() helper — all mocked, no live network calls."""
import os
from pathlib import Path

import pytest

from jd_matcher.errors import ConfigError
from jd_matcher.llm import get_openai_key


def test_get_openai_key_missing_raises_config_error(monkeypatch, tmp_path):
    """Missing key in env AND missing from .env raises ConfigError with actionable message."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Write an empty .env so dotenv finds a file but no key
    (tmp_path / ".env").write_text("")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError) as exc_info:
        get_openai_key()

    message = str(exc_info.value)
    assert "OPENAI_API_KEY" in message
    assert "SETUP.md" in message


def test_get_openai_key_present_returns_value(monkeypatch):
    """Key present in environment is returned as-is."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")

    result = get_openai_key()

    assert result == "sk-test123"


def test_get_openai_key_loads_from_dotenv(monkeypatch, tmp_path):
    """Key absent from os.environ but present in .env file is loaded and returned."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-fromdotenv\n")
    monkeypatch.chdir(tmp_path)

    result = get_openai_key()

    assert result == "sk-fromdotenv"
