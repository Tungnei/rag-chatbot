from __future__ import annotations

from pathlib import Path

import pytest

from rag_chatbot.retrieval import UnsupportedFormatError
from rag_chatbot.retrieval.document_retrieval import detect_source_type
from rag_chatbot.validate import SourceType


def test_detect_source_type():
    assert detect_source_type(Path("a.md")) is SourceType.MARKDOWN
    assert detect_source_type(Path("a.PDF")) is SourceType.PDF
    with pytest.raises(UnsupportedFormatError):
        detect_source_type(Path("a.docx"))


def test_ingest_text_file(pipeline, vector_store, sample_txt):
    assert pipeline.ingest_file(sample_txt) > 0
    assert vector_store.info().points_count > 0


def test_ingest_markdown_keeps_heading_as_title(pipeline, vector_store, sample_md, embedder):
    pipeline.ingest_file(sample_md)
    hits = vector_store.search(embedder.embed_query("Run uv sync"), top_k=5)
    assert {h.title for h in hits} & {"Setup", "Usage", "Guide"}


def test_reingesting_same_file_does_not_duplicate(pipeline, vector_store, sample_txt):
    first = pipeline.ingest_file(sample_txt)
    pipeline.ingest_file(sample_txt)
    assert vector_store.info().points_count == first


def test_ingest_directory_covers_supported_files(pipeline, sample_txt, sample_md, settings):
    (settings.storage.documents_dir / "ignored.docx").write_text("nope", encoding="utf-8")
    results = pipeline.ingest_directory(settings.storage.documents_dir)
    assert set(results) == {"faq.txt", "guide.md"}


def test_delete_by_source_leaves_other_sources(pipeline, vector_store, sample_txt, sample_md):
    pipeline.ingest_file(sample_txt)
    md_count = pipeline.ingest_file(sample_md)
    vector_store.delete_by_source("faq.txt")
    assert vector_store.info().points_count == md_count
