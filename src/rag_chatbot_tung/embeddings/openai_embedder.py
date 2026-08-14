"""OpenAI-backed implementation of EmbeddingProvider."""

from __future__ import annotations

import time

from openai import OpenAI, RateLimitError

from rag_chatbot_tung.configs import EmbeddingSettings
from rag_chatbot_tung.logging import get_logger

logger = get_logger(__name__)

_MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbedder:
    def __init__(self, settings: EmbeddingSettings, api_key: str) -> None:
        self._settings = settings
        self._client = OpenAI(api_key=api_key, base_url=settings.base_url or None)

    @property
    def dimension(self) -> int:
        return _MODEL_DIMENSIONS.get(self._settings.model, 1536)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        batch_size = self._settings.batch_size
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors.extend(self._embed_batch(batch))
            logger.debug("embedded %d/%d texts", len(vectors), len(texts))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]

    def health(self) -> bool:
        try:
            self.embed_query("ping")
        except Exception as exc:
            logger.warning("embedding health check failed: %s", exc)
            return False
        return True

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        delay = 1.0
        for attempt in range(self._settings.max_retries):
            try:
                response = self._client.embeddings.create(model=self._settings.model, input=batch)
            except RateLimitError:
                if attempt == self._settings.max_retries - 1:
                    raise
                logger.warning("rate limited, retrying in %.1fs", delay)
                time.sleep(delay)
                delay *= 2
            else:
                return [item.embedding for item in response.data]
        raise RuntimeError("unreachable")
