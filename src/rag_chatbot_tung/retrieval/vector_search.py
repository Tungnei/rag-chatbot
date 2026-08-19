"""Qdrant-backed implementation of VectorStore."""

from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient, models

from rag_chatbot_tung.adaptor import VectorPoint
from rag_chatbot_tung.configs import QdrantSettings, RetrieverSettings
from rag_chatbot_tung.logging import get_logger
from rag_chatbot_tung.retrieval.sparse import encode as encode_sparse
from rag_chatbot_tung.validate import (
    CollectionInfo,
    DocumentSummary,
    RetrievedChunk,
    SourceType,
)

logger = get_logger(__name__)

_SCROLL_PAGE = 256

_DENSE_VECTOR = "dense"
_SPARSE_VECTOR = "bm25"


class CollectionSchemaError(RuntimeError):
    """Raised when an existing collection predates the hybrid schema."""


def _coerce_source_type(value: object) -> SourceType:
    """Never let one odd payload take down a whole-collection sweep.

    `SourceType(...)` raises on an unknown value or an explicit null, which in
    `list_sources` would turn a single hand-written or future-version point into a
    500 for the entire endpoint.
    """
    if isinstance(value, str):
        try:
            return SourceType(value)
        except ValueError:
            pass
    logger.warning("unusable source_type %r in payload, treating as text", value)
    return SourceType.TEXT


class QdrantVectorStore:
    def __init__(
        self,
        settings: QdrantSettings,
        client: QdrantClient | None = None,
        retriever: RetrieverSettings | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or QdrantClient(url=settings.url, api_key=settings.api_key)
        # Defaults leave hybrid off, so a store built without retriever settings keeps
        # behaving exactly as it did before this phase.
        self._retriever = retriever or RetrieverSettings()

    @property
    def collection(self) -> str:
        return self._settings.collection_name

    def ensure_collection(self) -> None:
        if self._client.collection_exists(self.collection):
            # Returning early here used to mean a collection created before the hybrid
            # schema kept being used as-is, and every hybrid query then failed somewhere
            # far away from the cause. Fail loudly at startup instead.
            self._require_hybrid_schema()
            return
        self._client.create_collection(
            collection_name=self.collection,
            vectors_config={
                _DENSE_VECTOR: models.VectorParams(
                    size=self._settings.vector_size,
                    distance=models.Distance(self._settings.distance),
                )
            },
            sparse_vectors_config={
                # IDF is computed server-side, so the encoder only ships raw term
                # frequencies — that is what keeps BM25 free of a new dependency.
                _SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
        # Payload index keeps delete_by_source and source filtering fast as data grows.
        self._client.create_payload_index(
            collection_name=self.collection,
            field_name="source",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        logger.info("created qdrant collection %s", self.collection)

    def _require_hybrid_schema(self) -> None:
        """Reject a pre-hybrid collection, naming the command that fixes it."""
        params = self._client.get_collection(self.collection).config.params
        vectors = params.vectors
        if not isinstance(vectors, dict) or _DENSE_VECTOR not in vectors:
            raise CollectionSchemaError(
                f"collection '{self.collection}' uses the pre-hybrid unnamed vector "
                f"schema. Run: uv run python scripts/migrate_collection.py --yes"
            )
        if _SPARSE_VECTOR not in (params.sparse_vectors or {}):
            raise CollectionSchemaError(
                f"collection '{self.collection}' has no '{_SPARSE_VECTOR}' sparse "
                f"vector. Run: uv run python scripts/migrate_collection.py --yes"
            )

    def upsert(self, points: list[VectorPoint]) -> None:
        if not points:
            return
        self._client.upsert(
            collection_name=self.collection,
            points=[
                models.PointStruct(id=p.id, vector=self._vectors_of(p), payload=p.payload)
                for p in points
            ],
            wait=True,
        )
        logger.info("upserted %d points into %s", len(points), self.collection)

    def _vectors_of(self, point: VectorPoint) -> dict[str, Any]:
        # dict[str, Any] rather than a precise union: PointStruct's vector parameter is
        # a dict with a wide value union, and dict is invariant, so a narrower value
        # type is rejected outright even though every value we put in is valid.
        vectors: dict[str, Any] = {_DENSE_VECTOR: point.vector}
        if point.sparse is not None and point.sparse.indices:
            vectors[_SPARSE_VECTOR] = models.SparseVector(
                indices=point.sparse.indices, values=point.sparse.values
            )
        return vectors

    def search(
        self,
        vector: list[float],
        top_k: int,
        score_threshold: float | None = None,
        query_text: str | None = None,
    ) -> list[RetrievedChunk]:
        if query_text is not None and self._retriever.hybrid:
            return self._hybrid_search(vector, top_k, score_threshold, query_text)

        hits = self._client.query_points(
            collection_name=self.collection,
            query=vector,
            # Required now that vectors are named: omitting it raises rather than
            # silently searching the wrong thing.
            using=_DENSE_VECTOR,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        ).points

        return [
            RetrievedChunk(
                text=hit.payload.get("text", ""),
                score=hit.score,
                source=hit.payload.get("source", "unknown"),
                source_type=SourceType(hit.payload.get("source_type", "text")),
                index=hit.payload.get("index", 0),
                title=hit.payload.get("title"),
                page=hit.payload.get("page"),
            )
            for hit in hits
            if hit.payload
        ]

    def _hybrid_search(
        self,
        vector: list[float],
        top_k: int,
        score_threshold: float | None,
        query_text: str,
    ) -> list[RetrievedChunk]:
        """Dense and BM25 prefetches merged with reciprocal rank fusion.

        The cosine threshold goes INSIDE the dense prefetch, never on the fused query:
        an RRF score is a function of rank and list count, not of similarity, so
        applying a cosine-calibrated cutoff to it compares two different units and the
        effective rule would shift whenever a limit changed. The sparse prefetch gets
        no threshold because no BM25 cutoff has been measured yet, and an invented one
        is worse than none.
        """
        encoded = encode_sparse(query_text)
        query_sparse = models.SparseVector(indices=encoded.indices, values=encoded.values)

        response = self._client.query_points(
            collection_name=self.collection,
            prefetch=[
                models.Prefetch(
                    query=vector,
                    using=_DENSE_VECTOR,
                    limit=self._retriever.dense_prefetch_limit,
                    score_threshold=score_threshold,
                ),
                models.Prefetch(
                    query=query_sparse,
                    using=_SPARSE_VECTOR,
                    limit=self._retriever.sparse_prefetch_limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )

        allowed = self._grounded_ids(vector, score_threshold, query_sparse)
        return [self._to_chunk(hit) for hit in response.points if hit.payload and hit.id in allowed]

    def _grounded_ids(
        self,
        vector: list[float],
        score_threshold: float | None,
        query_sparse: models.SparseVector,
    ) -> set:
        """Ids a fused result is allowed to keep — the anti-fabrication floor (B2).

        BM25 matches on a single shared token, and stopwords are shared with every
        document, so fusion alone lets an off-topic question pull in unrelated
        passages. That would quietly disable the orchestrator's empty-result guard,
        and hit-rate cannot see it: hit-rate only asks whether the expected source
        appeared, never what junk came along.

        A chunk survives if the THRESHOLDED dense prefetch vouched for it, or if its
        BM25 score clears a measured floor.
        """
        dense_ids = {
            point.id
            for point in self._client.query_points(
                collection_name=self.collection,
                query=vector,
                using=_DENSE_VECTOR,
                limit=self._retriever.dense_prefetch_limit,
                score_threshold=score_threshold,
                with_payload=False,
            ).points
        }

        floor = self._retriever.sparse_score_floor
        if floor is None:
            return dense_ids

        sparse_ids = {
            point.id
            for point in self._client.query_points(
                collection_name=self.collection,
                query=query_sparse,
                using=_SPARSE_VECTOR,
                limit=self._retriever.sparse_prefetch_limit,
                score_threshold=floor,
                with_payload=False,
            ).points
        }
        return dense_ids | sparse_ids

    @staticmethod
    def _to_chunk(hit) -> RetrievedChunk:
        return RetrievedChunk(
            text=hit.payload.get("text", ""),
            score=hit.score,
            source=hit.payload.get("source", "unknown"),
            source_type=SourceType(hit.payload.get("source_type", "text")),
            index=hit.payload.get("index", 0),
            title=hit.payload.get("title"),
            page=hit.payload.get("page"),
        )

    def delete_by_source(self, source: str) -> None:
        self._client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(key="source", match=models.MatchValue(value=source))
                    ]
                )
            ),
            wait=True,
        )

    def list_sources(self) -> list[DocumentSummary]:
        """Every indexed source with its chunk count, sorted by name.

        Walks the collection page by page: Qdrant offers no distinct-value call that
        works in both server and local mode, and this stays O(number of chunks). Fine
        at the scale this project indexes; revisit with the facet API if it stops being.
        """
        summaries: dict[str, DocumentSummary] = {}
        offset: models.ExtendedPointId | None = None

        while True:
            points, offset = self._client.scroll(
                collection_name=self.collection,
                limit=_SCROLL_PAGE,
                offset=offset,
                with_payload=["source", "source_type", "title", "index"],
                # Counting chunks does not need their 1536-dim vectors.
                with_vectors=False,
            )

            for point in points:
                payload = point.payload or {}
                source = payload.get("source")
                if not source:
                    # No source means delete_by_source can never reach it, so listing it
                    # would only offer the user a delete button that does nothing.
                    logger.warning("skipping point %s: payload has no source", point.id)
                    continue

                existing = summaries.get(source)
                if existing is None:
                    existing = DocumentSummary(
                        source=source,
                        source_type=_coerce_source_type(payload.get("source_type")),
                        chunks=0,
                    )
                    summaries[source] = existing

                existing.chunks += 1
                # Markdown gives every chunk the heading it sits under, so only the
                # first chunk carries anything resembling a document title. Picking
                # whichever chunk arrived first would surface a random mid-document
                # section instead.
                if payload.get("index") == 0:
                    existing.title = payload.get("title")

            if offset is None:
                break

        # Sorted so the result does not depend on storage order, which differs
        # between the local client used in tests and a real Qdrant server.
        return [summaries[source] for source in sorted(summaries)]

    def info(self) -> CollectionInfo:
        info = self._client.get_collection(self.collection)
        return CollectionInfo(
            name=self.collection,
            points_count=info.points_count or 0,
            vector_size=self._settings.vector_size,
        )

    def health(self) -> bool:
        try:
            self._client.get_collections()
        except Exception as exc:
            logger.warning("qdrant health check failed: %s", exc)
            return False
        return True
