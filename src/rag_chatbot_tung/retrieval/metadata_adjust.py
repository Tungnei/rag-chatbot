"""Deterministic post-rerank adjustment: the last layer before the LLM.

Pure functions over a chunk list, no state and no model calls. That is the selection
criterion, not an accident: this layer sits behind an expensive cross-encoder, so it
has to be cheap enough to be free by comparison.

There is no recency rule here because the payload carries no timestamp — only source,
source_type, title, page and index. Adding one would mean re-ingesting everything.
"""

from __future__ import annotations

from itertools import groupby

from rag_chatbot_tung.configs import MetadataAdjustSettings
from rag_chatbot_tung.retrieval.sparse import tokenize
from rag_chatbot_tung.validate import RetrievedChunk


def _boost_titles(query: str, chunks: list[RetrievedChunk], boost: float) -> list[RetrievedChunk]:
    """Lift chunks whose heading shares a token with the query.

    Only the title counts. Boosting on body text would redo the job dense, BM25 and the
    cross-encoder each already did, and did better.

    The tokenizer is phase 7's, deliberately: one definition of "what a word is" and one
    NFKC normalisation shared with BM25. A second tokenizer here would plant a fresh
    normalisation asymmetry in the exact place one was just removed.
    """
    terms = set(tokenize(query))
    if not terms:
        return list(chunks)

    boosted = []
    for chunk in chunks:
        if chunk.title and terms & set(tokenize(chunk.title)):
            boosted.append(chunk.model_copy(update={"score": chunk.score + boost}))
        else:
            boosted.append(chunk)
    return boosted


def _merge_adjacent(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Rejoin consecutive chunks of the same source, restoring split context.

    Especially useful for PDFs, which are cut hard at page boundaries, so a sentence
    spanning two pages arrives mechanically halved.

    Three lossy choices, each deliberate:
    - score is the MAX of the parts, never the sum; summing would reward merging and
      corrupt the ranking.
    - page and title come from the lowest index. The citation can therefore point at
      the first page of a pair while the answer sits on the second — the UI renders
      that number, so it is a real, visible cost.
    """
    ordered = sorted(chunks, key=lambda c: (c.source, c.index))
    merged: list[RetrievedChunk] = []

    for _, group in groupby(ordered, key=lambda c: c.source):
        run: list[RetrievedChunk] = []
        for chunk in group:
            if run and chunk.index == run[-1].index + 1:
                run.append(chunk)
                continue
            if run:
                merged.append(_collapse(run))
            run = [chunk]
        if run:
            merged.append(_collapse(run))

    return merged


def _collapse(run: list[RetrievedChunk]) -> RetrievedChunk:
    if len(run) == 1:
        return run[0]

    head = run[0]  # lowest index, since the run was built in index order
    return head.model_copy(
        update={
            "text": "\n\n".join(c.text for c in run),
            "score": max(c.score for c in run),
        }
    )


def _cap_per_source(chunks: list[RetrievedChunk], limit: int) -> list[RetrievedChunk]:
    """At most `limit` chunks per source, preserving the incoming order.

    Without this one document can take every slot, so a question that needs two sources
    weighed against each other never receives both. The trade is deliberate: a document
    with three genuinely relevant chunks loses one, buying source diversity with depth.
    """
    seen: dict[str, int] = {}
    kept = []
    for chunk in chunks:
        count = seen.get(chunk.source, 0)
        if count >= limit:
            continue
        seen[chunk.source] = count + 1
        kept.append(chunk)
    return kept


def adjust(
    query: str,
    chunks: list[RetrievedChunk],
    settings: MetadataAdjustSettings,
    top_k: int,
) -> list[RetrievedChunk]:
    """Apply the metadata rules and cut to top_k.

    The order is the contract and must not be rearranged:

        boost -> sort -> merge -> cap -> cut

    - boost before sort, or the boost changes nothing.
    - the sort is stable, so tied scores keep the reranker's ordering rather than
      discarding work it just paid for.
    - merge before cap: capping first would trim entries and only then fuse them,
      leaving fewer chunks than intended.
    - cap before cut: cutting first lets the cap shrink the result below top_k with
      nobody left to fill the freed slots.

    When disabled this still cuts. It replaced the final `chunks[:top_k]`, so returning
    the input untouched would hand the LLM rerank.top_n chunks instead of top_k.
    """
    if not settings.enabled:
        return chunks[:top_k]

    adjusted = _boost_titles(query, chunks, settings.title_boost)
    adjusted = sorted(adjusted, key=lambda c: c.score, reverse=True)

    if settings.merge_adjacent:
        merged = _merge_adjacent(adjusted)
        # Merging reorders by (source, index), so restore the score ordering. Stable
        # again, so equal scores keep the order established above.
        adjusted = sorted(merged, key=lambda c: c.score, reverse=True)

    adjusted = _cap_per_source(adjusted, settings.max_per_source)
    return adjusted[:top_k]
