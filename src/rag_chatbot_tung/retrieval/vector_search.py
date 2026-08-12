"""Qdrant-backed implementation of VectorStore."""

from __future__ import annotations

from qdrant_client import QdrantClient, models

from rag_chatbot_tung.adaptor import VectorPoint
from rag_chatbot_tung.configs import QdrantSettings
from rag_chatbot_tung.logging import get_logger
from rag_chatbot_tung.validate import (
    CollectionInfo,
    DocumentSummary,
    RetrievedChunk,
    SourceType,
)

logger = get_logger(__name__)

_SCROLL_PAGE = 256


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
    def __init__(self, settings: QdrantSettings, client: QdrantClient | None = None) -> None:
        self._settings = settings
        self._client = client or QdrantClient(url=settings.url, api_key=settings.api_key)

    @property
    def collection(self) -> str:
        return self._settings.collection_name

    def ensure_collection(self) -> None:
        if self._client.collection_exists(self.collection):
            return
        self._client.create_collection(
            collection_name=self.collection,
            vectors_config=models.VectorParams(
                size=self._settings.vector_size,
                distance=models.Distance(self._settings.distance),
            ),
        )
        # Payload index keeps delete_by_source and source filtering fast as data grows.
        self._client.create_payload_index(
            collection_name=self.collection,
            field_name="source",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        logger.info("created qdrant collection %s", self.collection)

    def upsert(self, points: list[VectorPoint]) -> None:
        if not points:
            return
        self._client.upsert(
            collection_name=self.collection,
            points=[
                models.PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points
            ],
            wait=True,
        )
        logger.info("upserted %d points into %s", len(points), self.collection)

    def search(
        self, vector: list[float], top_k: int, score_threshold: float | None = None
    ) -> list[RetrievedChunk]:
        hits = self._client.query_points(
            collection_name=self.collection,
            query=vector,
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
