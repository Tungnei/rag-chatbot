from __future__ import annotations

import pytest

from rag_chatbot_tung.llm_generator import NO_CONTEXT_ANSWER
from rag_chatbot_tung.validate import IngestRequest, QueryRequest


def test_answer_without_indexed_documents_skips_llm(orchestrator, llm):
    response = orchestrator.answer(QueryRequest(question="anything?"))
    assert response.answer == NO_CONTEXT_ANSWER
    assert llm.messages == []


def test_answer_uses_retrieved_context(orchestrator, sample_txt, llm):
    orchestrator.ingest(IngestRequest(path=str(sample_txt)))
    response = orchestrator.answer(QueryRequest(question="Q: What database is used?"))

    assert response.answer == llm.reply
    assert response.tokens_used == 18
    assert response.sources
    assert "Qdrant" in llm.messages[0][1]["content"]


def test_include_sources_false_hides_sources(orchestrator, sample_txt):
    orchestrator.ingest(IngestRequest(path=str(sample_txt)))
    response = orchestrator.answer(
        QueryRequest(question="Q: What database is used?", include_sources=False)
    )
    assert response.sources == []


def test_ingest_resolves_bare_filename_against_documents_dir(orchestrator, sample_txt):
    assert orchestrator.ingest(IngestRequest(path="faq.txt")).chunks_indexed > 0


def test_ingest_missing_file_raises(orchestrator):
    with pytest.raises(FileNotFoundError):
        orchestrator.ingest(IngestRequest(path="nope.txt"))


def test_ingest_request_requires_exactly_one_source():
    with pytest.raises(ValueError):
        IngestRequest()
    with pytest.raises(ValueError):
        IngestRequest(path="a.txt", url="https://example.com")


def test_health_reports_ok(orchestrator):
    health = orchestrator.health("1.2.3")
    assert (health.status, health.qdrant, health.openai, health.version) == (
        "ok",
        True,
        True,
        "1.2.3",
    )
