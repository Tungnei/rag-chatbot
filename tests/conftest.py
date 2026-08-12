from __future__ import annotations

import hashlib

import pytest
from qdrant_client import QdrantClient

from rag_chatbot_tung.chunking import TextSplitter
from rag_chatbot_tung.configs import Settings
from rag_chatbot_tung.orchestrator import RAGOrchestrator
from rag_chatbot_tung.retrieval import IngestionPipeline, QdrantVectorStore
from rag_chatbot_tung.validate import GenerationResult

VECTOR_SIZE = 16


class FakeEmbedder:
    """Deterministic hash-based embeddings so tests never call OpenAI."""

    dimension = VECTOR_SIZE

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def health(self) -> bool:
        return True

    @staticmethod
    def _vector(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [digest[i] / 255.0 for i in range(VECTOR_SIZE)]


class FakeLLM:
    def __init__(self, reply: str = "generated answer [1]") -> None:
        self.reply = reply
        self.messages: list[list[dict[str, str]]] = []

    def generate(self, messages: list[dict[str, str]]) -> GenerationResult:
        self.messages.append(messages)
        return GenerationResult(
            text=self.reply, model="fake-model", prompt_tokens=11, completion_tokens=7
        )

    def health(self) -> bool:
        return True


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(openai_api_key="test-key")
    s.qdrant.vector_size = VECTOR_SIZE
    s.qdrant.collection_name = "test_documents"
    s.storage.documents_dir = tmp_path / "documents"
    s.storage.upload_dir = tmp_path / "uploads"
    s.storage.documents_dir.mkdir(parents=True)
    return s


@pytest.fixture
def vector_store(settings) -> QdrantVectorStore:
    store = QdrantVectorStore(settings.qdrant, client=QdrantClient(":memory:"))
    store.ensure_collection()
    return store


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def pipeline(embedder, vector_store, settings) -> IngestionPipeline:
    return IngestionPipeline(embedder, vector_store, TextSplitter(settings.chunking))


@pytest.fixture
def orchestrator(settings, embedder, vector_store, llm) -> RAGOrchestrator:
    return RAGOrchestrator(settings, embedder=embedder, vector_store=vector_store, llm=llm)


@pytest.fixture
def sample_txt(settings):
    path = settings.storage.documents_dir / "faq.txt"
    path.write_text(
        "Q: What database is used?\nA: Qdrant stores the vectors.\n\n"
        "Q: What embedding model?\nA: text-embedding-3-small with 1536 dimensions.\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def sample_md(settings):
    path = settings.storage.documents_dir / "guide.md"
    path.write_text(
        "# Guide\n\nIntro paragraph about the guide.\n\n"
        "## Setup\n\nRun uv sync to install dependencies.\n\n"
        "## Usage\n\nSend a POST request to the query endpoint.\n",
        encoding="utf-8",
    )
    return path
