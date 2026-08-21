"""Cross-encoder reranking, behind the optional `rerank` extra.

A cross-encoder reads the (question, passage) pair together instead of comparing two
independently encoded vectors, so it catches relevance that both dense and BM25 miss.
It is also the layer that cleans up what fusion leaves behind: the sparse prefetch has
no threshold, so the fused candidates always contain a few very weak matches.
"""

from __future__ import annotations

from rag_chatbot.configs import RerankSettings
from rag_chatbot.validate import RetrievedChunk


class CrossEncoderReranker:
    def __init__(self, settings: RerankSettings) -> None:
        # Imported here, not at module scope: importing this package must not drag in
        # torch. The whole suite runs offline and has to keep doing so even once a
        # ~2GB dependency exists somewhere in the tree. A test enforces this.
        from sentence_transformers import CrossEncoder

        self._settings = settings
        self._model = CrossEncoder(settings.model, device=settings.device)

    def rerank(self, query: str, chunks: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]:
        if not chunks:
            return []

        scores = self._model.predict([(query, c.text) for c in chunks])
        # The chunk's own score field is overwritten with the cross-encoder score, so
        # what the UI renders after this point is on a different scale than cosine.
        rescored = [
            c.model_copy(update={"score": float(s)}) for c, s in zip(chunks, scores, strict=True)
        ]
        rescored.sort(key=lambda c: c.score, reverse=True)
        return rescored[:top_n]
