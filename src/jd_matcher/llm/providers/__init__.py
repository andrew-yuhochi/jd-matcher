"""LLM provider implementations for jd-matcher.

Callers import from here or from jd_matcher.llm directly — never from openai.
"""

from jd_matcher.llm.providers.factory import make_embedder, make_extractor

__all__ = ["make_extractor", "make_embedder"]
