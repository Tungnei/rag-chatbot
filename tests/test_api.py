from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_chatbot_tung.api.app import create_app
from rag_chatbot_tung.llm_generator import NO_CONTEXT_ANSWER


@pytest.fixture
def client(settings, orchestrator):
    with TestClient(create_app(settings, orchestrator=orchestrator)) as c:
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["qdrant"] and body["openai"]


def test_query_without_documents(client):
    body = client.post("/query", json={"question": "hello?"}).json()
    assert body["answer"] == NO_CONTEXT_ANSWER
    assert body["sources"] == []


def test_ingest_then_query(client, sample_txt, llm):
    ingested = client.post("/ingest", json={"path": "faq.txt"}).json()
    assert ingested["chunks_indexed"] > 0

    body = client.post("/query", json={"question": "What database is used?"}).json()
    assert body["answer"] == llm.reply
    assert body["sources"][0]["source"] == "faq.txt"


def test_ingest_missing_file_returns_404(client):
    assert client.post("/ingest", json={"path": "nope.txt"}).status_code == 404


def test_ingest_requires_exactly_one_source(client):
    assert client.post("/ingest", json={}).status_code == 422
    assert client.post("/ingest", json={"path": "a.txt", "url": "https://x.dev"}).status_code == 422


def test_upload_indexes_file(client):
    response = client.post(
        "/ingest/upload",
        files={"file": ("notes.md", b"# Notes\n\nSome indexable content in this file.")},
    )
    assert response.json()["chunks_indexed"] > 0


def test_upload_rejects_unsupported_format(client):
    response = client.post("/ingest/upload", files={"file": ("a.docx", b"binary")})
    assert response.status_code == 415


def test_upload_strips_directory_traversal(client, settings):
    client.post("/ingest/upload", files={"file": ("../../evil.md", b"# Evil\n\nContent here.")})
    assert (settings.storage.upload_dir / "evil.md").is_file()


def test_empty_question_rejected(client):
    assert client.post("/query", json={"question": ""}).status_code == 422


def test_delete_document(client, sample_txt):
    client.post("/ingest", json={"path": "faq.txt"})
    assert client.delete("/documents", params={"source": "faq.txt"}).status_code == 204
    assert client.get("/collections").json()["points_count"] == 0
