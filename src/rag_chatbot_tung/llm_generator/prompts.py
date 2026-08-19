"""Prompt construction for grounded RAG answers."""

from __future__ import annotations

from rag_chatbot_tung.utils import count_tokens, truncate_to_tokens
from rag_chatbot_tung.validate import RetrievedChunk, Turn

NO_CONTEXT_ANSWER = "I could not find anything relevant to that question in the indexed documents."

SYSTEM_PROMPT = f"""You are a precise question-answering assistant.

Rules:
- Answer using ONLY the numbered context passages provided by the user.
- Cite the passages you used with their bracket numbers, e.g. [1] or [2][3].
- If the passages do not contain the answer, reply exactly: "{NO_CONTEXT_ANSWER}"
- Never invent facts, sources, or citations.
- Earlier conversation turns are context for understanding the current question ONLY.
  They are not evidence: never treat a previous turn as a source, and never cite one.
- Answer in the same language the question is asked in."""

# Three exchanges (DEC-2). The cap lives here rather than on the Pydantic field so an
# over-long history is trimmed and answered, not rejected with a 422.
_MAX_HISTORY_ITEMS = 6


def format_context(chunks: list[RetrievedChunk], token_budget: int, model: str) -> str:
    """Render chunks as numbered passages, dropping the weakest once the budget is spent."""
    parts: list[str] = []
    used = 0
    for number, chunk in enumerate(chunks, start=1):
        location = f", page {chunk.page}" if chunk.page else ""
        heading = f" — {chunk.title}" if chunk.title else ""
        block = f"[{number}] ({chunk.source}{location}{heading})\n{chunk.text}"
        cost = count_tokens(block, model)
        if used + cost > token_budget and parts:
            break
        parts.append(block)
        used += cost
    return "\n\n".join(parts)


def _normalise_history(history: list[Turn]) -> list[Turn]:
    """Force client-supplied history into a strictly alternating user/assistant run.

    Anthropic requires alternating roles and `_split_system` forwards this list
    verbatim, so a history ending in `user` would put two user messages back to back.
    Collapsing same-role runs has to happen FIRST: dropping only a leading assistant
    and a trailing user leaves `[user, user, assistant]` untouched, which is exactly
    the shape that breaks alternation.
    """
    collapsed: list[Turn] = []
    for turn in history:
        if collapsed and collapsed[-1].role == turn.role:
            collapsed[-1] = turn  # keep the most recent of a same-role run
        else:
            collapsed.append(turn)

    # A conversation cannot open with the model speaking.
    while collapsed and collapsed[0].role == "assistant":
        collapsed.pop(0)
    # The current question is the final user turn, so history must not end on one.
    while collapsed and collapsed[-1].role == "user":
        collapsed.pop()
    return collapsed


def _fit_history(history: list[Turn], budget: int, model: str) -> list[dict[str, str]]:
    """Drop oldest turns until the history fits, truncating a single oversized turn.

    Trimming to the last six happens before normalisation: cutting afterwards could
    re-expose a leading assistant turn that normalisation had already removed.
    """
    turns = _normalise_history(history[-_MAX_HISTORY_ITEMS:])

    while turns and sum(count_tokens(t.content, model) for t in turns) > budget:
        if len(turns) == 1:
            clipped = truncate_to_tokens(turns[0].content, budget, model)
            turns = [turns[0].model_copy(update={"content": clipped})]
            break
        turns.pop(0)

    return [{"role": t.role, "content": t.content} for t in turns]


def build_rag_messages(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[Turn] | None = None,
    token_budget: int = 6000,
    history_budget: int = 1500,
    model: str = "gpt-4o-mini",
) -> list[dict[str, str]]:
    history_messages = _fit_history(history or [], history_budget, model)

    # History is charged against the shared budget first so three long turns can never
    # starve the retrieved passages — a failure that looks exactly like bad retrieval.
    history_used = sum(count_tokens(m["content"], model) for m in history_messages)
    context = format_context(chunks, max(token_budget - history_used, 0), model)

    user_content = f"Context passages:\n\n{context}\n\nQuestion: {question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history_messages,
        {"role": "user", "content": user_content},
    ]
