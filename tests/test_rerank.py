from __future__ import annotations

import subprocess
import sys

from rag_chatbot_tung.adaptor import Reranker
from rag_chatbot_tung.rerank import NoopReranker
from rag_chatbot_tung.validate import QueryRequest, RetrievedChunk, SourceType


def chunk(text: str, index: int, score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        text=text, score=score, source="faq.txt", source_type=SourceType.TEXT, index=index
    )


class RecordingReranker:
    """Test double kept here rather than in conftest: only this file uses it."""

    def __init__(self, reverse: bool = False) -> None:
        self.calls: list[tuple[str, int, int]] = []
        self.reverse = reverse

    def rerank(self, query: str, chunks: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]:
        self.calls.append((query, len(chunks), top_n))
        ordered = list(reversed(chunks)) if self.reverse else list(chunks)
        return ordered[:top_n]


def ingest_several(pipeline, settings) -> None:
    """Several distinct chunks, because order and fan-out are unobservable with one.

    The shared sample_txt fixture collapses into a single chunk, so a test built on it
    would pass or fail for reasons unrelated to reranking.
    """
    for name, body in (
        ("db.txt", "Qdrant stores the vectors for this system."),
        ("emb.txt", "The embedding model is text-embedding-3-small with 1536 dimensions."),
        ("api.txt", "The query endpoint accepts a question and returns an answer."),
        ("ops.txt", "Start the vector database before starting the web application."),
    ):
        path = settings.storage.documents_dir / name
        path.write_text(body, encoding="utf-8")
        pipeline.ingest_file(path)


def test_noop_preserves_order_and_cuts():
    chunks = [chunk(f"c{i}", i) for i in range(5)]

    result = NoopReranker().rerank("q", chunks, top_n=3)

    assert [c.text for c in result] == ["c0", "c1", "c2"]


def test_noop_handles_fewer_chunks_than_top_n():
    chunks = [chunk("a", 0), chunk("b", 1)]

    assert len(NoopReranker().rerank("q", chunks, top_n=10)) == 2


def test_noop_handles_empty_list():
    assert NoopReranker().rerank("q", [], top_n=5) == []


def test_noop_satisfies_the_protocol():
    assert isinstance(NoopReranker(), Reranker)


def test_importing_rerank_package_does_not_import_torch():
    """The suite must keep running offline even with a ~2GB dependency in the tree.

    Checked in a clean subprocess: the pytest process has already imported a hundred
    things, so inspecting sys.modules in-process would depend on test ordering rather
    than on what importing this package actually pulls in.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import rag_chatbot_tung.rerank; "
            "print('torch' in sys.modules, 'sentence_transformers' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "False False"


def test_orchestrator_applies_reranker(settings, embedder, vector_store, llm, pipeline, sample_txt):
    from rag_chatbot_tung.orchestrator import RAGOrchestrator

    pipeline.ingest_file(sample_txt)
    reranker = RecordingReranker()
    orchestrator = RAGOrchestrator(
        settings, embedder=embedder, vector_store=vector_store, llm=llm, reranker=reranker
    )

    orchestrator.answer(QueryRequest(question="What database is used?"))

    assert len(reranker.calls) == 1
    query, _, top_n = reranker.calls[0]
    assert query == "What database is used?"
    assert top_n >= settings.rerank.top_n


def test_reranker_not_called_when_no_chunks(settings, embedder, vector_store, llm):
    """Rerank runs after the empty check: calling a model to hand back an empty list
    wastes time and would erode the empty-result guard."""
    from rag_chatbot_tung.orchestrator import RAGOrchestrator

    reranker = RecordingReranker()
    orchestrator = RAGOrchestrator(
        settings, embedder=embedder, vector_store=vector_store, llm=llm, reranker=reranker
    )

    orchestrator.answer(QueryRequest(question="nothing is indexed"))

    assert reranker.calls == []


def test_reranker_output_flows_into_sources(settings, embedder, vector_store, llm, pipeline):
    """Proves rerank drives what the LLM and the user see, rather than running and
    then being discarded."""
    from rag_chatbot_tung.orchestrator import RAGOrchestrator

    ingest_several(pipeline, settings)
    plain = RAGOrchestrator(settings, embedder=embedder, vector_store=vector_store, llm=llm)
    baseline = plain.answer(QueryRequest(question="What database is used?")).sources

    reversed_ranker = RecordingReranker(reverse=True)
    orchestrator = RAGOrchestrator(
        settings,
        embedder=embedder,
        vector_store=vector_store,
        llm=llm,
        reranker=reversed_ranker,
    )
    reordered = orchestrator.answer(QueryRequest(question="What database is used?")).sources

    assert len(baseline) > 1, "need more than one source for order to be observable"
    assert [s.snippet for s in reordered] != [s.snippet for s in baseline]


def test_injected_reranker_gets_the_full_fan_out(settings, embedder, vector_store, llm, pipeline):
    """H5: a reranker injected directly must still receive the fused candidate pool.

    Deriving "are we reranking?" from settings.rerank.provider alone would leave an
    injected reranker fed only top_k candidates — it would reorder 5 into 5 and the
    entire point of reranking would vanish, with every other test still green.
    """
    from rag_chatbot_tung.orchestrator import RAGOrchestrator

    ingest_several(pipeline, settings)
    settings.rerank.provider = "noop"  # deliberately left at the default
    reranker = RecordingReranker()
    orchestrator = RAGOrchestrator(
        settings, embedder=embedder, vector_store=vector_store, llm=llm, reranker=reranker
    )

    orchestrator.answer(QueryRequest(question="What database is used?", top_k=1))

    _, candidates_seen, _ = reranker.calls[0]
    assert candidates_seen > 1, "reranker was fed top_k candidates instead of the fused pool"


def test_top_n_never_drops_below_requested_top_k(
    settings, embedder, vector_store, llm, pipeline, sample_txt
):
    """H5b: top_k accepts up to 20 while rerank.top_n defaults to 10.

    Without the guard a user raising the slider to 20 would silently get 10.
    """
    from rag_chatbot_tung.orchestrator import RAGOrchestrator

    pipeline.ingest_file(sample_txt)
    reranker = RecordingReranker()
    orchestrator = RAGOrchestrator(
        settings, embedder=embedder, vector_store=vector_store, llm=llm, reranker=reranker
    )

    orchestrator.answer(QueryRequest(question="What database is used?", top_k=20))

    _, _, top_n = reranker.calls[0]
    assert top_n >= 20
