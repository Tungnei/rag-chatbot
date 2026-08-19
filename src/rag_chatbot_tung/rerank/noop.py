"""The default reranker: keeps fusion order, costs nothing, imports nothing."""

from __future__ import annotations

from rag_chatbot_tung.validate import RetrievedChunk


class NoopReranker:
    """Keeps the fusion order and cuts to top_n."""

    def rerank(self, query: str, chunks: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]:
        return chunks[:top_n]
