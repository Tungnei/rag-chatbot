"""Token counting via tiktoken."""

from __future__ import annotations

from functools import lru_cache

import tiktoken


@lru_cache
def _encoding(model: str) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    return len(_encoding(model).encode(text))


def truncate_to_tokens(text: str, max_tokens: int, model: str = "gpt-4o-mini") -> str:
    enc = _encoding(model)
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return enc.decode(tokens[:max_tokens])
