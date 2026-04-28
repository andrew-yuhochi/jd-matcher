"""Ollama LLMExtractor stub — placeholder for the M3 local-vs-cloud benchmark.

This stub raises ``NotImplementedError`` on instantiation so that any accidental
use during M2 fails loudly rather than silently doing nothing.

When the M3 benchmark sub-task is implemented, replace the body of
``OllamaExtractor`` with a real implementation that calls the Ollama REST API
at ``http://localhost:11434``.  The factory and all call sites require NO code
changes — switching provider is a config-only change (set
``config/llm.yaml: extraction.provider: ollama``).
"""

from __future__ import annotations

from jd_matcher.llm.providers.base import (
    ExtractionMetadata,
    LLMExtractor,
)


class OllamaExtractor:
    """Stub implementation — not yet available (M3 benchmark sub-task).

    Raises ``NotImplementedError`` on every method call.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(
            "OllamaExtractor is not implemented yet. "
            "It is planned for the M3 cloud-vs-local benchmark sub-task. "
            "To use a local model, wait for that task or contribute the implementation."
        )

    @classmethod
    def from_config(
        cls,
        provider: str | None = None,
        model: str | None = None,
        db_path: object = None,
    ) -> "LLMExtractor":
        raise NotImplementedError(
            "OllamaExtractor is not implemented yet. "
            "It is planned for the M3 cloud-vs-local benchmark sub-task. "
            "To use a local model, wait for that task or contribute the implementation."
        )

    def extract(
        self,
        prompt: str,
        system: str,
        response_format: dict,
    ) -> tuple[str, ExtractionMetadata]:
        raise NotImplementedError(
            "OllamaExtractor is not implemented yet. "
            "It is planned for the M3 cloud-vs-local benchmark sub-task."
        )
