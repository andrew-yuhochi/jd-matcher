"""LLM provider configuration loader for C28.

Reads ``config/llm.yaml`` at the project root (path relative to this file's
location: providers/ → llm/ → jd_matcher/ → src/ → project root).  The file
is optional — if absent, baked-in defaults are used so the tool works
out-of-the-box for cloud OpenAI without any YAML setup.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# providers/config.py → providers/ → llm/ → jd_matcher/ → src/ → project root
_DEFAULT_CONFIG_PATH = Path(__file__).parents[4] / "config" / "llm.yaml"


class ProviderConfig(BaseModel):
    provider: str = "openai"
    model: str


class LLMConfig(BaseModel):
    extraction: ProviderConfig = ProviderConfig(provider="openai", model="gpt-4o-mini")
    embedding: ProviderConfig = ProviderConfig(
        provider="openai", model="text-embedding-3-small"
    )


def load_llm_config(path: Path | None = None) -> LLMConfig:
    """Load LLM provider config from YAML, falling back to defaults if absent.

    Args:
        path: Override the default config path.  Useful in tests.

    Returns:
        A validated ``LLMConfig`` instance.
    """
    resolved = path if path is not None else _DEFAULT_CONFIG_PATH

    if not resolved.exists():
        logger.debug("load_llm_config: %s not found — using defaults", resolved)
        return LLMConfig()

    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        config = LLMConfig.model_validate(raw)
        logger.debug("load_llm_config: loaded from %s", resolved)
        return config
    except Exception as exc:
        logger.warning(
            "load_llm_config: failed to parse %s (%s) — using defaults", resolved, exc
        )
        return LLMConfig()
