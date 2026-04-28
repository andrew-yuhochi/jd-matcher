"""Ollama EmbeddingProvider stub — placeholder for the M3 local-vs-cloud benchmark.

When the M3 benchmark sub-task is implemented, replace the body of
``OllamaEmbedding`` with a real implementation backed by sentence-transformers
or the Ollama embedding API.  The factory requires NO code changes.
"""

from __future__ import annotations

from jd_matcher.llm.providers.base import (
    EmbeddingMetadata,
    EmbeddingProvider,
)


class OllamaEmbedding:
    """Stub implementation — not yet available (M3 benchmark sub-task).

    Raises ``NotImplementedError`` on every method call.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(
            "OllamaEmbedding is not implemented yet. "
            "It is planned for the M3 cloud-vs-local benchmark sub-task. "
            "To use local embeddings, wait for that task or contribute the implementation."
        )

    @classmethod
    def from_config(
        cls,
        provider: str | None = None,
        model: str | None = None,
        db_path: object = None,
    ) -> "EmbeddingProvider":
        raise NotImplementedError(
            "OllamaEmbedding is not implemented yet. "
            "It is planned for the M3 cloud-vs-local benchmark sub-task. "
            "To use local embeddings, wait for that task or contribute the implementation."
        )

    def embed(
        self,
        texts: list[str],
    ) -> tuple[list[list[float]], EmbeddingMetadata]:
        raise NotImplementedError(
            "OllamaEmbedding is not implemented yet. "
            "It is planned for the M3 cloud-vs-local benchmark sub-task."
        )
