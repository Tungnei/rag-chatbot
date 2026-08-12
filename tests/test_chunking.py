from __future__ import annotations

from rag_chatbot_tung.chunking import TextSplitter
from rag_chatbot_tung.configs import ChunkingSettings


def make_splitter(**kw) -> TextSplitter:
    return TextSplitter(ChunkingSettings(**kw))


def test_short_text_stays_one_chunk():
    assert make_splitter().split("A single short paragraph.") == ["A single short paragraph."]


def test_chunks_respect_max_size():
    text = "\n\n".join(f"Paragraph number {i} with some filler words." * 3 for i in range(20))
    chunks = make_splitter(chunk_size=200, chunk_overlap=20).split(text)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_no_chunk_starts_mid_word():
    text = " ".join(f"word{i}" for i in range(300))
    for chunk in make_splitter(chunk_size=100, chunk_overlap=30).split(text):
        assert chunk.split()[0].startswith("word")


def test_tiny_trailing_chunk_is_merged():
    text = "A" * 95 + "\n\nxy"
    chunks = make_splitter(chunk_size=100, chunk_overlap=0, min_chunk_size=50).split(text)
    assert len(chunks) == 1


def test_markdown_split_attaches_heading():
    md = "# Title\n\nIntro text here.\n\n## Setup\n\nInstall the dependencies first.\n"
    pairs = make_splitter().split_markdown(md)
    assert [h for _, h in pairs] == ["Title", "Setup"]


def test_heading_without_body_is_dropped():
    md = "# Top\n\n## Empty\n\n### Real\n\nActual content lives here.\n"
    headings = [h for _, h in make_splitter().split_markdown(md)]
    assert "Empty" not in headings
    assert "Real" in headings
