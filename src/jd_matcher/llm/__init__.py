import os
from pathlib import Path

from dotenv import load_dotenv

from jd_matcher.errors import ConfigError
from jd_matcher.llm.providers.base import (
    EmbeddingMetadata,
    EmbeddingProvider,
    ExtractionMetadata,
    LLMExtractor,
    LLMProviderError,
    ProviderUnavailableError,
    RateLimitError,
)


def get_openai_key() -> str:
    """Return the OpenAI API key from the environment.

    Searches for .env starting at the current working directory so tests can
    chdir to a tmp_path with a fixture .env.  Shell-exported vars take
    precedence over .env (standard 12-factor convention: .env fills defaults
    for unset vars only, never overwrites operator-set values).
    Raises ConfigError with an actionable message when the key is absent.
    """
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ConfigError(
            "OPENAI_API_KEY is not set. Add it to your .env file "
            "(see docs/poc/SETUP.md §4 'OpenAI API key setup' for how to obtain one)."
        )
    return key


# Attach from_config() classmethods to the Protocol objects so the demo
# artifact ``LLMExtractor.from_config()`` and ``EmbeddingProvider.from_config()``
# work without callers ever importing from the providers package.


def _llm_extractor_from_config(
    cls: type,
    provider: str | None = None,
    model: str | None = None,
    db_path: object = None,
) -> LLMExtractor:
    from jd_matcher.llm.providers.factory import make_extractor
    from pathlib import Path as _Path

    resolved_db = _Path(db_path) if isinstance(db_path, str) else db_path
    return make_extractor(provider=provider, model=model, db_path=resolved_db)


def _embedding_provider_from_config(
    cls: type,
    provider: str | None = None,
    model: str | None = None,
    db_path: object = None,
) -> EmbeddingProvider:
    from jd_matcher.llm.providers.factory import make_embedder
    from pathlib import Path as _Path

    resolved_db = _Path(db_path) if isinstance(db_path, str) else db_path
    return make_embedder(provider=provider, model=model, db_path=resolved_db)


import types as _types  # noqa: E402

# Attach as class methods on the Protocol class objects so callers can use
# LLMExtractor.from_config() without importing from providers directly.
LLMExtractor.from_config = classmethod(  # type: ignore[method-assign]
    lambda cls, provider=None, model=None, db_path=None: _llm_extractor_from_config(
        cls, provider, model, db_path
    )
)
EmbeddingProvider.from_config = classmethod(  # type: ignore[method-assign]
    lambda cls, provider=None, model=None, db_path=None: _embedding_provider_from_config(
        cls, provider, model, db_path
    )
)

__all__ = [
    "get_openai_key",
    "LLMExtractor",
    "EmbeddingProvider",
    "ExtractionMetadata",
    "EmbeddingMetadata",
    "RateLimitError",
    "ProviderUnavailableError",
    "LLMProviderError",
]
