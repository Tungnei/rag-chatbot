from __future__ import annotations

import pytest

from rag_chatbot_tung.llm_generator import NO_CONTEXT_ANSWER
from rag_chatbot_tung.utils import count_tokens
from rag_chatbot_tung.validate import IngestRequest, QueryRequest, Turn


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


def test_answer_passes_history_to_the_llm(orchestrator, pipeline, sample_txt, llm):
    pipeline.ingest_file(sample_txt)

    orchestrator.answer(
        QueryRequest(
            question="What database is used?",
            history=[
                Turn(role="user", content="Tell me about storage."),
                Turn(role="assistant", content="Qdrant holds the vectors."),
            ],
        )
    )

    sent = llm.messages[0]
    assert len(sent) >= 4
    assert any("Qdrant holds the vectors." == m["content"] for m in sent)


def test_history_does_not_change_the_embedded_query(orchestrator, pipeline, sample_txt, llm):
    """DEC-2 enforced mechanically: only the current question is ever embedded.

    Appending history to the embedded string is query-rewriting through the back
    door, which DEC-2 blocks until phase 5 produces evidence. Asserting on
    FakeEmbedder.calls would prove nothing — it records embed_texts, not
    embed_query — so this spies on embed_query directly.
    """
    pipeline.ingest_file(sample_txt)

    embedded: list[str] = []
    original = orchestrator.embedder.embed_query
    orchestrator.embedder.embed_query = lambda text: (  # type: ignore[method-assign]
        embedded.append(text),
        original(text),
    )[1]

    first = orchestrator.answer(QueryRequest(question="What database is used?"))
    second = orchestrator.answer(
        QueryRequest(
            question="What database is used?",
            history=[
                Turn(role="user", content="totally unrelated chatter about the weather"),
                Turn(role="assistant", content="more unrelated chatter about tomatoes"),
            ],
        )
    )

    assert embedded == ["What database is used?", "What database is used?"]
    assert [s.source for s in first.sources] == [s.source for s in second.sources]
    assert [s.score for s in first.sources] == [s.score for s in second.sources]


def test_history_does_not_leak_between_requests(orchestrator, pipeline, sample_txt, llm):
    """RAGOrchestrator is a process-wide singleton; history must stay per-request."""
    pipeline.ingest_file(sample_txt)

    orchestrator.answer(
        QueryRequest(
            question="What database is used?",
            history=[
                Turn(role="user", content="earlier question"),
                Turn(role="assistant", content="earlier answer"),
            ],
        )
    )
    orchestrator.answer(QueryRequest(question="What database is used?"))

    assert len(llm.messages[1]) == 2
    assert "earlier answer" not in llm.messages[1][-1]["content"]


def test_history_budget_setting_is_actually_wired(orchestrator, pipeline, sample_txt, llm):
    """Guards a silent break: configs and build_rag_messages both default to 1500, so
    dropping the argument at the call site would leave every other test green while
    every env override was quietly ignored.
    """
    pipeline.ingest_file(sample_txt)
    orchestrator.settings.llm.history_token_budget = 5

    orchestrator.answer(
        QueryRequest(
            question="What database is used?",
            history=[
                Turn(role="user", content="short"),
                Turn(role="assistant", content="word " * 500),
            ],
        )
    )

    history_messages = llm.messages[0][1:-1]
    used = sum(count_tokens(m["content"], "gpt-4o-mini") for m in history_messages)
    assert used <= 5, f"history_token_budget=5 ignored, {used} tokens sent"
