"""Wires retrieval and generation into the public RAG operations."""

from __future__ import annotations

import time
from pathlib import Path

from rag_chatbot.adaptor import EmbeddingProvider, LLMProvider, Reranker, VectorStore
from rag_chatbot.chunking import TextSplitter
from rag_chatbot.configs import Settings
from rag_chatbot.llm_generator import NO_CONTEXT_ANSWER, build_rag_messages
from rag_chatbot.logging import get_logger
from rag_chatbot.providers import build_embedder, build_llm, build_reranker
from rag_chatbot.retrieval import IngestionPipeline, QdrantVectorStore
from rag_chatbot.retrieval.metadata_adjust import adjust as adjust_metadata
from rag_chatbot.validate import (
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
        reranker: Reranker | None = None,
    ) -> None:
        self.settings = settings
        self.embedder = embedder or build_embedder(settings)
        self.vector_store = vector_store or QdrantVectorStore(
            settings.qdrant, retriever=settings.retriever
        )
        self.llm = llm or build_llm(settings)
        self.reranker = reranker or build_reranker(settings)
        # An injected reranker counts too. Deriving this from the setting alone would
        # feed a directly-injected reranker only top_k candidates — it would reorder
        # five into five and every test checking 'was it called' would still pass.
        self._reranks = reranker is not None or settings.rerank.provider != "noop"
        self.pipeline = IngestionPipeline(
            self.embedder, self.vector_store, TextSplitter(settings.chunking)
        )

    def startup(self) -> None:
        self.vector_store.ensure_collection()

    def _effective_top_n(self, top_k: int) -> int:
        """top_k accepts up to 20 while rerank.top_n defaults to 10; never return less
        than the caller asked for."""
        return max(self.settings.rerank.top_n, top_k)

    def retrieve(self, question: str, top_k: int) -> list[RetrievedChunk]:
        """The single retrieval path. answer() and evaluate_retrieval() both call this.

        Keeping one path is the point: the eval used to reimplement retrieval by
        calling vector_store.search directly, so a new layer added to answer() would
        never have been measured — the comparison table would print the same numbers
        for every configuration.
        """
        # Fan out only when something will consume the extra candidates; with the
        # default NoopReranker this stays exactly the phase-7 behaviour.
        fan_out = self.settings.retriever.fusion_limit if self._reranks else top_k

        chunks = self.vector_store.search(
            self.embedder.embed_query(question),
            top_k=fan_out,
            score_threshold=self.settings.retriever.score_threshold,
            # Only the BM25 branch reads this; the dense vector above is still built
            # from the current question alone (DEC-2).
            query_text=question,
        )
        if not chunks:
            return []

        # After the empty check, never before: running a model to hand back an empty
        # list wastes time and weakens the empty-result guard.
        chunks = self.reranker.rerank(question, chunks, self._effective_top_n(top_k))

        # Replaces the final cut rather than sitting beside it — when the adjustment
        # rules are disabled this still trims to top_k, so turning the layer off cannot
        # accidentally hand the LLM rerank.top_n chunks instead.
        return adjust_metadata(question, chunks, self.settings.metadata_adjust, top_k)

    def answer(self, request: QueryRequest) -> QueryResponse:
        started = time.perf_counter()
        top_k = request.top_k or self.settings.retriever.top_k

        chunks = self.retrieve(request.question, top_k)

        if not chunks:
            # history_turns is counted through the log, never through a field on
            # self: RAGOrchestrator is a process-wide singleton, so a counter here
            # would bleed across every request and every test sharing the fixture.
            logger.info(
                "no chunks above threshold (history_turns=%d) for question: %s",
                len(request.history),
                request.question[:80],
            )
            return QueryResponse(
                answer=NO_CONTEXT_ANSWER,
                model=self.settings.llm.model,
                latency_ms=self._elapsed_ms(started),
            )

        result = self.llm.generate(
            build_rag_messages(
                request.question,
                chunks,
                request.history,
                token_budget=self.settings.llm.context_token_budget,
                history_budget=self.settings.llm.history_token_budget,
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
