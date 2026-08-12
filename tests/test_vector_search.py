from __future__ import annotations

from rag_chatbot_tung.adaptor import VectorPoint
from rag_chatbot_tung.validate import SourceType

PAYLOAD = {
    "text": "Qdrant stores the vectors.",
    "source": "faq.txt",
    "source_type": "text",
    "index": 0,
    "title": None,
    "page": None,
}


def make_point(pid: str, value: float, **payload_overrides) -> VectorPoint:
    return VectorPoint(id=pid, vector=[value] * 16, payload={**PAYLOAD, **payload_overrides})


def test_search_returns_typed_chunks(vector_store):
    vector_store.upsert([make_point("00000000-0000-0000-0000-000000000001", 0.5)])
    hits = vector_store.search([0.5] * 16, top_k=3)
    assert len(hits) == 1
    assert hits[0].source_type is SourceType.TEXT
    assert hits[0].text == PAYLOAD["text"]


def test_score_threshold_filters_weak_matches(vector_store):
    vector_store.upsert([make_point("00000000-0000-0000-0000-000000000002", 0.5)])
    assert vector_store.search([-0.5] * 16, top_k=3, score_threshold=0.9) == []


def test_upsert_with_same_id_replaces(vector_store):
    pid = "00000000-0000-0000-0000-000000000003"
    vector_store.upsert([make_point(pid, 0.5)])
    vector_store.upsert([make_point(pid, 0.5, text="updated text")])
    assert vector_store.info().points_count == 1
    assert vector_store.search([0.5] * 16, top_k=1)[0].text == "updated text"


def test_empty_upsert_is_noop(vector_store):
    vector_store.upsert([])
    assert vector_store.info().points_count == 0


def test_health(vector_store):
    assert vector_store.health() is True
