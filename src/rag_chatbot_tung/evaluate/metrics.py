"""Retrieval metrics for comparing chunking and top_k settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rag_chatbot_tung.orchestrator import RAGOrchestrator


@dataclass(slots=True)
class EvalCase:
    question: str
    expected_source: str


@dataclass(slots=True)
class EvalReport:
    total: int
    hits: int
    reciprocal_rank_sum: float

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total if self.total else 0.0

    @property
    def mrr(self) -> float:
        return self.reciprocal_rank_sum / self.total if self.total else 0.0


def load_cases(path: Path) -> list[EvalCase]:
    """Read a JSONL file of {"question": ..., "expected_source": ...} records."""
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(EvalCase(**json.loads(line)))
    return cases


def evaluate_retrieval(
    orchestrator: RAGOrchestrator, cases: list[EvalCase], top_k: int | None = None
) -> EvalReport:
    k = top_k or orchestrator.settings.retriever.top_k
    hits = 0
    rr_sum = 0.0

    for case in cases:
        chunks = orchestrator.vector_store.search(
            orchestrator.embedder.embed_query(case.question),
            top_k=k,
            score_threshold=orchestrator.settings.retriever.score_threshold,
        )
        for rank, chunk in enumerate(chunks, start=1):
            if chunk.source == case.expected_source:
                hits += 1
                rr_sum += 1 / rank
                break

    return EvalReport(total=len(cases), hits=hits, reciprocal_rank_sum=rr_sum)
