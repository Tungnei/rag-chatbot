"""Document loaders and the ingestion pipeline that feeds the vector store."""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from rag_chatbot_tung.adaptor import EmbeddingProvider, VectorPoint, VectorStore
from rag_chatbot_tung.chunking import TextSplitter
from rag_chatbot_tung.logging import get_logger
from rag_chatbot_tung.utils import clean_text
from rag_chatbot_tung.validate import Chunk, SourceType

logger = get_logger(__name__)

_EXTENSION_TYPES = {
    ".txt": SourceType.TEXT,
    ".md": SourceType.MARKDOWN,
    ".markdown": SourceType.MARKDOWN,
    ".pdf": SourceType.PDF,
}

_STRIPPED_TAGS = ("script", "style", "nav", "header", "footer", "aside", "noscript")

# Deterministic namespace so re-ingesting the same chunk reuses the same point id.
_POINT_NAMESPACE = uuid.UUID("6f1a4b7e-0a3d-4a2a-9c1b-1d5c9f2e8a10")


class UnsupportedFormatError(ValueError):
    pass


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_pdf(path: Path) -> list[tuple[int, str]]:
    """Return (page_number, text) pairs so page numbers survive into chunk metadata."""
    reader = PdfReader(str(path))
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((number, text))
    return pages


def load_url(url: str, timeout: float = 30.0) -> tuple[str, str | None]:
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(_STRIPPED_TAGS):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    return soup.get_text(separator="\n"), title


def detect_source_type(path: Path) -> SourceType:
    source_type = _EXTENSION_TYPES.get(path.suffix.lower())
    if source_type is None:
        raise UnsupportedFormatError(
            f"unsupported file type '{path.suffix}'; supported: {sorted(_EXTENSION_TYPES)}"
        )
    return source_type


class IngestionPipeline:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
        splitter: TextSplitter,
    ) -> None:
        self._embedder = embedder
        self._store = vector_store
        self._splitter = splitter

    def ingest_file(self, path: Path) -> int:
        source_type = detect_source_type(path)
        source = path.name

        if source_type is SourceType.PDF:
            chunks = self._chunk_pdf(path, source)
        elif source_type is SourceType.MARKDOWN:
            chunks = self._chunk_markdown(clean_text(load_text(path)), source)
        else:
            chunks = self._chunk_plain(clean_text(load_text(path)), source, SourceType.TEXT)

        return self._index(source, chunks)

    def ingest_url(self, url: str) -> int:
        raw, title = load_url(url)
        chunks = self._chunk_plain(clean_text(raw), url, SourceType.URL, title=title)
        return self._index(url, chunks)

    def ingest_directory(self, directory: Path) -> dict[str, int]:
        results: dict[str, int] = {}
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _EXTENSION_TYPES:
                continue
            results[path.name] = self.ingest_file(path)
        return results

    def _chunk_plain(
        self,
        text: str,
        source: str,
        source_type: SourceType,
        title: str | None = None,
        page: int | None = None,
        start_index: int = 0,
    ) -> list[Chunk]:
        return [
            Chunk(
                text=piece,
                index=start_index + i,
                source=source,
                source_type=source_type,
                title=title,
                page=page,
            )
            for i, piece in enumerate(self._splitter.split(text))
        ]

    def _chunk_markdown(self, text: str, source: str) -> list[Chunk]:
        return [
            Chunk(
                text=piece,
                index=i,
                source=source,
                source_type=SourceType.MARKDOWN,
                title=heading,
            )
            for i, (piece, heading) in enumerate(self._splitter.split_markdown(text))
        ]

    def _chunk_pdf(self, path: Path, source: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        for page_number, raw in load_pdf(path):
            chunks.extend(
                self._chunk_plain(
                    clean_text(raw),
                    source,
                    SourceType.PDF,
                    page=page_number,
                    start_index=len(chunks),
                )
            )
        return chunks

    def _index(self, source: str, chunks: list[Chunk]) -> int:
        if not chunks:
            logger.warning("no chunks produced for %s", source)
            return 0

        vectors = self._embedder.embed_texts([c.text for c in chunks])
        points = [
            VectorPoint(
                id=str(uuid.uuid5(_POINT_NAMESPACE, f"{source}:{chunk.index}")),
                vector=vector,
                payload=chunk.model_dump(mode="json"),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]

        self._store.delete_by_source(source)
        self._store.upsert(points)
        logger.info("indexed %d chunks from %s", len(points), source)
        return len(points)
