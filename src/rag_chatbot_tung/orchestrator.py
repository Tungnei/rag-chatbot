"""Wires retrieval and generation into the public RAG operations."""

from __future__ import annotations

import time
from pathlib import Path

from rag_chatbot_tung.adaptor import EmbeddingProvider, LLMProvider, VectorStore
from rag_chatbot_tung.chunking import TextSplitter
from rag_chatbot_tung.configs import Settings
from rag_chatbot_tung.llm_generator import NO_CONTEXT_ANSWER, build_rag_messages
from rag_chatbot_tung.logging import get_logger
from rag_chatbot_tung.providers import build_embedder, build_llm
from rag_chatbot_tung.retrieval import IngestionPipeline, QdrantVectorStore
from rag_chatbot_tung.validate import (
    CollectionInfo,
    DocumentList,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    RetrievedChunk,
    Source,
)

logger = get_logger(__name__)

_SNIPPET_LENGTH = 240


class RAGOrchestrator:
    def __init__(
        self,
        settings: Settings,
        embedder: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self.settings = settings
        self.embedder = embedder or build_embedder(settings)
        self.vector_store = vector_store or QdrantVectorStore(settings.qdrant)
        self.llm = llm or build_llm(settings)
        self.pipeline = IngestionPipeline(
            self.embedder, self.vector_store, TextSplitter(settings.chunking)
        )

    def startup(self) -> None:
        self.vector_store.ensure_collection()

    def answer(self, request: QueryRequest) -> QueryResponse:
        started = time.perf_counter()
        top_k = request.top_k or self.settings.retriever.top_k

        chunks = self.vector_store.search(
            self.embedder.embed_query(request.question),
            top_k=top_k,
            score_threshold=self.settings.retriever.score_threshold,
        )

        if not chunks:
            logger.info("no chunks above threshold for question: %s", request.question[:80])
            return QueryResponse(
                answer=NO_CONTEXT_ANSWER,
                model=self.settings.llm.model,
                latency_ms=self._elapsed_ms(started),
            )

        result = self.llm.generate(
            build_rag_messages(
                request.question,
                chunks,
                token_budget=self.settings.llm.context_token_budget,
                model=self.settings.llm.model,
            )
        )

        return QueryResponse(
            answer=result.text,
            sources=self._to_sources(chunks) if request.include_sources else [],
            model=result.model,
            tokens_used=result.total_tokens,
            latency_ms=self._elapsed_ms(started),
        )

    def ingest(self, request: IngestRequest) -> IngestResponse:
        if request.url:
            count = self.pipeline.ingest_url(request.url)
            return IngestResponse(source=request.url, chunks_indexed=count)

        path = Path(request.path or "")
        if not path.is_absolute():
            path = self.settings.storage.documents_dir / path.name
        if not path.is_file():
            raise FileNotFoundError(f"file not found: {path}")

        count = self.pipeline.ingest_file(path)
        return IngestResponse(source=path.name, chunks_indexed=count)

    def ingest_directory(self, directory: Path | None = None) -> dict[str, int]:
        return self.pipeline.ingest_directory(directory or self.settings.storage.documents_dir)

    def delete_source(self, source: str) -> None:
        self.vector_store.delete_by_source(source)

    def list_documents(self) -> DocumentList:
        documents = self.vector_store.list_sources()
        return DocumentList(documents=documents, total=len(documents))

    def collection_info(self) -> CollectionInfo:
        return self.vector_store.info()

    def health(self, version: str) -> HealthResponse:
        qdrant_ok = self.vector_store.health()
        openai_ok = self.llm.health()
        return HealthResponse(
            status="ok" if qdrant_ok and openai_ok else "degraded",
            qdrant=qdrant_ok,
            openai=openai_ok,
            version=version,
        )

    @staticmethod
    def _to_sources(chunks: list[RetrievedChunk]) -> list[Source]:
        return [
            Source(
                source=chunk.source,
                snippet=chunk.text[:_SNIPPET_LENGTH],
                score=chunk.score,
                page=chunk.page,
            )
            for chunk in chunks
        ]

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
