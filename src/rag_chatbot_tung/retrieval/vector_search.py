"""Qdrant-backed implementation of VectorStore."""

from __future__ import annotations

from qdrant_client import QdrantClient, models

from rag_chatbot_tung.adaptor import VectorPoint
from rag_chatbot_tung.configs import QdrantSettings
from rag_chatbot_tung.logging import get_logger
from rag_chatbot_tung.validate import CollectionInfo, RetrievedChunk, SourceType

logger = get_logger(__name__)


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
