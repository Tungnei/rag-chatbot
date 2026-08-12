"""Prompt construction for grounded RAG answers."""

from __future__ import annotations

from rag_chatbot_tung.utils import count_tokens
from rag_chatbot_tung.validate import RetrievedChunk

NO_CONTEXT_ANSWER = "I could not find anything relevant to that question in the indexed documents."

SYSTEM_PROMPT = f"""You are a precise question-answering assistant.

Rules:
- Answer using ONLY the numbered context passages provided by the user.
- Cite the passages you used with their bracket numbers, e.g. [1] or [2][3].
- If the passages do not contain the answer, reply exactly: "{NO_CONTEXT_ANSWER}"
- Never invent facts, sources, or citations.
- Answer in the same language the question is asked in."""


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


def build_rag_messages(
    question: str,
    chunks: list[RetrievedChunk],
    token_budget: int = 6000,
    model: str = "gpt-4o-mini",
) -> list[dict[str, str]]:
    context = format_context(chunks, token_budget, model)
    user_content = f"Context passages:\n\n{context}\n\nQuestion: {question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
