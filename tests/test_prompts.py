from __future__ import annotations

from rag_chatbot_tung.llm_generator.prompts import build_rag_messages, format_context
from rag_chatbot_tung.validate import RetrievedChunk, SourceType


def chunk(text: str, index: int = 0, page: int | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        score=0.9,
        source="faq.txt",
        source_type=SourceType.TEXT,
        index=index,
        page=page,
    )


def test_context_is_numbered_and_labels_source():
    context = format_context([chunk("first"), chunk("second", 1)], 1000, "gpt-4o-mini")
    assert "[1] (faq.txt)" in context
    assert "[2] (faq.txt)" in context


def test_page_number_is_included():
    assert "page 7" in format_context([chunk("x", page=7)], 1000, "gpt-4o-mini")


def test_context_is_truncated_to_budget():
    chunks = [chunk("filler " * 200, i) for i in range(10)]
    context = format_context(chunks, 100, "gpt-4o-mini")
    assert context.count("(faq.txt)") == 1


def test_messages_carry_system_rules_and_question():
    messages = build_rag_messages("What database?", [chunk("Qdrant")])
    assert messages[0]["role"] == "system"
    assert "ONLY" in messages[0]["content"]
    assert "What database?" in messages[1]["content"]
