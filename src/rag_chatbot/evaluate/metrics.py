"""Retrieval metrics for comparing chunking and top_k settings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rag_chatbot.orchestrator import RAGOrchestrator


@dataclass(slots=True)
class EvalCase:
    question: str
    # None marks an off-topic case: retrieving nothing is the correct outcome. Hit-rate
    # alone is blind to junk returned for such a question, which is exactly the failure
    # BM25 introduces, so these are scored separately.
    expected_source: str | None
    # Both fields carry defaults so the pre-existing two-key qa.jsonl still loads.
    question_selfcontained: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class EvalCaseResult:
    """One case's outcome, kept so two eval runs can be diffed case by case.

    A stable overall hit-rate can hide five cases flipping to miss while five others
    flip to hit; only per-case detail surfaces that.
    """

    # The case's canonical question, always the `question` field even when the
    # self-contained phrasing was the one actually embedded. Without it a pronoun run
    # and a self-contained run share no key, and --baseline reports every case as
    # "gained" while the hit-rate visibly falls.
    case_id: str
    question: str
    expected_source: str | None
    hit: bool
    rank: int | None
    scores: list[float]
    sources: list[str]

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "question": self.question,
            "expected_source": self.expected_source,
            "hit": self.hit,
            "rank": self.rank,
            "scores": self.scores,
            "sources": self.sources,
        }


@dataclass(slots=True)
class EvalReport:
    total: int
    hits: int
    reciprocal_rank_sum: float
    results: list[EvalCaseResult] = field(default_factory=list)
    # Off-topic cases are counted apart from hit_rate: folding two kinds of question
    # into one ratio hides the very thing these cases exist to expose.
    abstain_correct: int = 0
    false_positive: int = 0

    @property
    def scored(self) -> int:
        """Cases with an expected source — the denominator hit_rate/mrr belong to."""
        return self.total - self.abstain_correct - self.false_positive

    @property
    def hit_rate(self) -> float:
        return self.hits / self.scored if self.scored else 0.0

    @property
    def mrr(self) -> float:
        return self.reciprocal_rank_sum / self.scored if self.scored else 0.0

    @property
    def offtopic_total(self) -> int:
        return self.abstain_correct + self.false_positive

    @property
    def abstain_rate(self) -> float:
        return self.abstain_correct / self.offtopic_total if self.offtopic_total else 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "scored": self.scored,
            "hits": self.hits,
            "hit_rate": self.hit_rate,
            "mrr": self.mrr,
            "abstain_correct": self.abstain_correct,
            "false_positive": self.false_positive,
            "abstain_rate": self.abstain_rate,
            "results": [r.to_dict() for r in self.results],
        }


def load_cases(path: Path) -> list[EvalCase]:
    """Read a JSONL file of eval records into cases."""
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(EvalCase(**json.loads(line)))
    return cases


def evaluate_retrieval(
    orchestrator: RAGOrchestrator,
    cases: list[EvalCase],
    top_k: int | None = None,
    *,
    selfcontained: bool = False,
) -> EvalReport:
    """Score retrieval over `cases`.

    `selfcontained` swaps in the pronoun-free phrasing of each case, which is how the
    multi-turn A/B is run: the same set twice, differing only in that wording.
    """
    k = top_k or orchestrator.settings.retriever.top_k
    hits = 0
    rr_sum = 0.0
    abstain_correct = 0
    false_positive = 0
    results: list[EvalCaseResult] = []

    for case in cases:
        question = case.question_selfcontained if selfcontained else case.question
        question = question or case.question

        # Goes through the orchestrator's own retrieval path rather than reaching
        # into the vector store. Reimplementing retrieval here is how a new layer ends
        # up never being measured, with the comparison table printing identical numbers
        # for every configuration and the conclusion reading "the layer is useless".
        chunks = orchestrator.retrieve(question, k)
        scores = [c.score for c in chunks]
        sources = [c.source for c in chunks]

        if case.expected_source is None:
            # Off-topic: returning nothing is the win condition.
            if chunks:
                false_positive += 1
            else:
                abstain_correct += 1
            results.append(
                EvalCaseResult(
                    case_id=case.question,
                    question=question,
                    expected_source=None,
                    hit=not chunks,
                    rank=None,
                    scores=scores,
                    sources=sources,
                )
            )
            continue

        rank: int | None = None
        for position, chunk in enumerate(chunks, start=1):
            if chunk.source == case.expected_source:
                rank = position
                hits += 1
                rr_sum += 1 / position
                break

        results.append(
            EvalCaseResult(
                case_id=case.question,
                question=question,
                expected_source=case.expected_source,
                hit=rank is not None,
                rank=rank,
                scores=scores,
                sources=sources,
            )
        )

    return EvalReport(
        total=len(cases),
        hits=hits,
        reciprocal_rank_sum=rr_sum,
        results=results,
        abstain_correct=abstain_correct,
        false_positive=false_positive,
    )
