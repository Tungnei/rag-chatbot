"""Pydantic models shared between the API layer and the RAG pipeline."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SourceType(StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    PDF = "pdf"
    URL = "url"


class Chunk(BaseModel):
    """A piece of a document, ready to be embedded."""

    text: str
    index: int
    source: str
    source_type: SourceType
    title: str | None = None
    page: int | None = None


class RetrievedChunk(BaseModel):
    text: str
    score: float
    source: str
    source_type: SourceType
    index: int
    title: str | None = None
    page: int | None = None


class Source(BaseModel):
    source: str
    snippet: str
    score: float
    page: int | None = None


class GenerationResult(BaseModel):
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class Turn(BaseModel):
    """One past exchange. `system` is deliberately not allowed: a client must not be
    able to inject its own instructions into the prompt."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    include_sources: bool = True
    # The business limit is three exchanges (DEC-2), enforced by TRIMMING in
    # build_rag_messages so an over-long history is answered rather than rejected.
    # This cap is an abuse stop instead: without it a client could post 10k turns of
    # 4k chars and have 40MB parsed into memory before we ever get to trim it.
    history: list[Turn] = Field(default_factory=list, max_length=50)


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source] = Field(default_factory=list)
    model: str
    tokens_used: int = 0
    latency_ms: int = 0


class IngestRequest(BaseModel):
    path: str | None = None
    url: str | None = None

    @model_validator(mode="after")
    def exactly_one_source(self) -> IngestRequest:
        if bool(self.path) == bool(self.url):
            raise ValueError("provide exactly one of 'path' or 'url'")
        return self


class IngestResponse(BaseModel):
    source: str
    chunks_indexed: int
    status: str = "ok"


class DocumentSummary(BaseModel):
    """One indexed source and how many chunks it currently occupies."""

    source: str
    source_type: SourceType
    chunks: int
    title: str | None = None


class DocumentList(BaseModel):
    documents: list[DocumentSummary]
    # Number of sources, not of chunks — `CollectionInfo.points_count` is the chunk count.
    total: int


class CollectionInfo(BaseModel):
    name: str
    points_count: int
    vector_size: int


class HealthResponse(BaseModel):
    status: str
    qdrant: bool
    openai: bool
    version: str
