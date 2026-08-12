"""Structural interfaces for the pluggable parts of the RAG pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from rag_chatbot_tung.validate import CollectionInfo, GenerationResult, RetrievedChunk


@dataclass(slots=True)
class VectorPoint:
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def health(self) -> bool: ...


@runtime_checkable
class VectorStore(Protocol):
    def ensure_collection(self) -> None: ...

    def upsert(self, points: list[VectorPoint]) -> None: ...

    def search(
        self, vector: list[float], top_k: int, score_threshold: float | None = None
    ) -> list[RetrievedChunk]: ...

    def delete_by_source(self, source: str) -> None: ...

    def info(self) -> CollectionInfo: ...

    def health(self) -> bool: ...


@runtime_checkable
class LLMProvider(Protocol):
    def generate(self, messages: list[dict[str, str]]) -> GenerationResult: ...

    def health(self) -> bool: ...
