from __future__ import annotations

import unicodedata

from rag_chatbot_tung.configs import MetadataAdjustSettings
from rag_chatbot_tung.retrieval.metadata_adjust import adjust
from rag_chatbot_tung.validate import RetrievedChunk, SourceType


def chunk(
    source: str,
    index: int,
    score: float,
    text: str = "body",
    title: str | None = None,
    page: int | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        score=score,
        source=source,
        source_type=SourceType.TEXT,
        index=index,
        title=title,
        page=page,
    )


def settings(**overrides) -> MetadataAdjustSettings:
    base = {"enabled": True, "max_per_source": 2, "merge_adjacent": True, "title_boost": 0.05}
    return MetadataAdjustSettings(**{**base, **overrides})


def test_cap_per_source_keeps_the_best_n():
    # Non-consecutive indices so this exercises the cap alone, not merging.
    chunks = [chunk("a.txt", i * 2, score=1.0 - i / 10) for i in range(5)]

    result = adjust("q", chunks, settings(merge_adjacent=False), top_k=10)

    assert len(result) == 2
    assert [c.score for c in result] == [1.0, 0.9]


def test_cap_per_source_does_not_touch_other_sources():
    chunks = [
        chunk(src, i * 2, score=1.0 - i / 10)
        for src in ("a.txt", "b.txt", "c.txt")
        for i in range(3)
    ]

    result = adjust("q", chunks, settings(merge_adjacent=False), top_k=99)

    assert len(result) == 6
    for src in ("a.txt", "b.txt", "c.txt"):
        assert sum(1 for c in result if c.source == src) == 2


def test_merge_adjacent_joins_consecutive_indices():
    chunks = [chunk("a.txt", 4, 0.9, text="first half"), chunk("a.txt", 5, 0.8, text="second half")]

    result = adjust("q", chunks, settings(), top_k=10)

    assert len(result) == 1
    assert result[0].text == "first half\n\nsecond half"


def test_merge_adjacent_ignores_gaps():
    chunks = [chunk("a.txt", 4, 0.9), chunk("a.txt", 6, 0.8)]

    assert len(adjust("q", chunks, settings(), top_k=10)) == 2


def test_merge_adjacent_ignores_different_sources():
    chunks = [chunk("a.txt", 4, 0.9), chunk("b.txt", 5, 0.8)]

    assert len(adjust("q", chunks, settings(), top_k=10)) == 2


def test_merged_chunk_keeps_max_score_and_first_page():
    """A known, deliberate loss: the citation points at the first page of the pair.

    Max rather than sum — summing would reward merging and corrupt the ranking.
    """
    chunks = [chunk("a.txt", 4, 0.4, page=3, title="Intro"), chunk("a.txt", 5, 0.9, page=4)]

    result = adjust("q", chunks, settings(), top_k=10)

    assert result[0].score == 0.9
    assert result[0].page == 3
    assert result[0].title == "Intro"


def test_merge_is_order_independent():
    """Without this the rule is deterministic on paper but input-order dependent."""
    a = chunk("a.txt", 4, 0.4, text="first")
    b = chunk("a.txt", 5, 0.9, text="second")
    c = chunk("b.txt", 0, 0.7, text="other")

    forward = adjust("q", [a, b, c], settings(), top_k=10)
    backward = adjust("q", [c, b, a], settings(), top_k=10)

    assert [(x.source, x.index, x.text, x.score) for x in forward] == [
        (x.source, x.index, x.text, x.score) for x in backward
    ]


def test_title_boost_applies_on_token_match():
    chunks = [chunk("a.txt", 0, 0.50, title="Cài đặt Qdrant")]

    result = adjust("cài đặt thế nào", chunks, settings(merge_adjacent=False), top_k=10)

    assert result[0].score == 0.55


def test_title_boost_is_case_and_unicode_insensitive():
    """Reuses phase 7's tokenizer, so NFC/NFD and case both fold.

    A second tokenizer written here would reintroduce the normalisation asymmetry
    that phase 7 just removed, and this test is what would catch it.
    """
    nfd_title = unicodedata.normalize("NFD", "Cài Đặt")
    chunks = [chunk("a.txt", 0, 0.50, title=nfd_title)]

    result = adjust(
        unicodedata.normalize("NFC", "cài đặt"), chunks, settings(merge_adjacent=False), top_k=10
    )

    assert result[0].score == 0.55


def test_title_boost_skips_chunks_without_title():
    # .txt sources carry no title at all, which must not raise.
    chunks = [chunk("a.txt", 0, 0.50, title=None)]

    result = adjust("anything", chunks, settings(merge_adjacent=False), top_k=10)

    assert result[0].score == 0.50


def test_no_boost_from_text_match():
    """Boosting on body text would redo what dense, BM25 and the reranker each did."""
    chunks = [chunk("a.txt", 0, 0.50, text="cài đặt qdrant ở đây", title="Something Else")]

    result = adjust("cài đặt", chunks, settings(merge_adjacent=False), top_k=10)

    assert result[0].score == 0.50


def test_pipeline_order_is_boost_sort_merge_cap_cut():
    """The only test holding the five-step sequence together.

    Built so a different order gives a different answer: the boost is what lifts the
    titled chunk above its neighbour, merging then collapses a consecutive pair whose
    combined presence would otherwise consume the per-source cap, and the cap has to
    run before the cut or the final list silently shrinks below top_k.
    """
    chunks = [
        chunk("a.txt", 0, 0.50, text="a0", title="Cài đặt"),
        chunk("a.txt", 1, 0.52, text="a1"),
        chunk("a.txt", 5, 0.51, text="a5"),
        chunk("b.txt", 0, 0.49, text="b0"),
        chunk("c.txt", 0, 0.48, text="c0"),
    ]

    result = adjust("cài đặt", chunks, settings(), top_k=3)

    # a0 boosted to 0.55, so a0+a1 merge into one chunk scoring 0.55; a5 is the second
    # a.txt entry, filling the cap; b0 and c0 follow; the cut leaves three.
    assert len(result) == 3
    assert result[0].text == "a0\n\na1"
    assert result[0].score == 0.55
    assert sum(1 for c in result if c.source == "a.txt") <= 2


def test_disabled_only_cuts():
    """H1: switching the layer off must not switch off the cut.

    This layer replaced the final `chunks[:top_k]`, so returning the input untouched
    would push rerank.top_n chunks into the LLM — ten instead of five — and phase 10's
    third row would then run with double the context of the other three.
    """
    chunks = [chunk("a.txt", i, 1.0 - i / 100, title="Cài đặt") for i in range(10)]

    result = adjust("cài đặt", chunks, settings(enabled=False), top_k=5)

    assert len(result) == 5
    assert [c.score for c in result] == [c.score for c in chunks[:5]]
    assert [c.text for c in result] == [c.text for c in chunks[:5]]


def test_orchestrator_applies_metadata_adjust_after_rerank(
    settings, embedder, vector_store, llm, pipeline
):
    """End to end: ten candidates from the reranker must arrive as at most top_k,
    with no source occupying more than max_per_source slots."""
    from rag_chatbot_tung.orchestrator import RAGOrchestrator
    from rag_chatbot_tung.validate import QueryRequest

    for name in ("alpha.txt", "beta.txt", "gamma.txt"):
        for i in range(3):
            path = settings.storage.documents_dir / f"{name[:-4]}-{i}.txt"
            path.write_text(f"Qdrant stores vectors, part {i} of {name}.", encoding="utf-8")
            pipeline.ingest_file(path)

    settings.metadata_adjust.enabled = True
    settings.metadata_adjust.max_per_source = 2
    settings.retriever.top_k = 5

    orchestrator = RAGOrchestrator(settings, embedder=embedder, vector_store=vector_store, llm=llm)
    response = orchestrator.answer(QueryRequest(question="Where are vectors stored?"))

    assert len(response.sources) <= 5
    counts: dict[str, int] = {}
    for source in response.sources:
        counts[source.source] = counts.get(source.source, 0) + 1
    assert all(n <= 2 for n in counts.values()), counts
