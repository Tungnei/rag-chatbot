"""Structural interfaces for the pluggable parts of the RAG pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from rag_chatbot_tung.validate import (
    CollectionInfo,
    DocumentSummary,
    GenerationResult,
    RetrievedChunk,
)


@dataclass(slots=True)
class SparseVector:
    """Term indices and their weights, in the adaptor's own vocabulary.

    Translating this into the vector database's representation belongs to the store
    implementation — this layer stays free of infrastructure imports.
    """

    indices: list[int]
    values: list[float]


@dataclass(slots=True)
class VectorPoint:
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)
    sparse: SparseVector | None = None


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
        self,
        vector: list[float],
        top_k: int,
        score_threshold: float | None = None,
        query_text: str | None = None,
    ) -> list[RetrievedChunk]: ...

    def delete_by_source(self, source: str) -> None: ...

    def list_sources(self) -> list[DocumentSummary]: ...

    def info(self) -> CollectionInfo: ...

    def health(self) -> bool: ...


@runtime_checkable
class LLMProvider(Protocol):
    def generate(self, messages: list[dict[str, str]]) -> GenerationResult: ...

    def health(self) -> bool: ...


@runtime_checkable
class Reranker(Protocol):
    def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]: ...
