from __future__ import annotations

from rag_chatbot_tung.utils import (
    clean_text,
    count_tokens,
    normalize_whitespace,
    truncate_to_tokens,
)


def test_normalize_collapses_spaces_and_blank_lines():
    assert normalize_whitespace("a   b\n\n\n\nc  ") == "a b\n\nc"


def test_clean_text_strips_control_characters():
    assert clean_text("héllo\x00 world") == "héllo world"


def test_count_and_truncate_tokens():
    text = "word " * 100
    assert count_tokens(text) > 10
    assert count_tokens(truncate_to_tokens(text, 10)) == 10


def test_truncate_leaves_short_text_untouched():
    assert truncate_to_tokens("short", 100) == "short"
