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


def point_id(number: int) -> str:
    return f"00000000-0000-0000-0000-{number:012d}"


def test_list_sources_empty(vector_store):
    assert vector_store.list_sources() == []


def test_list_sources_groups_by_source(vector_store):
    # 300 chunks in one source pushes past the 256-point scroll page, so the
    # pagination branch actually runs. A single-page fixture would leave it
    # untested and still green.
    points = [make_point(point_id(n), 0.5, source="faq.txt", index=n) for n in range(300)]
    points += [
        make_point(point_id(1000 + n), 0.4, source="guide.md", index=n, title="Guide")
        for n in range(3)
    ]
    vector_store.upsert(points)

    documents = vector_store.list_sources()

    assert [doc.source for doc in documents] == ["faq.txt", "guide.md"]
    assert documents[0].chunks == 300
    assert documents[1].chunks == 3
    assert documents[1].title == "Guide"


def test_list_sources_after_delete(vector_store):
    vector_store.upsert(
        [
            make_point(point_id(1), 0.5, source="faq.txt"),
            make_point(point_id(2), 0.4, source="guide.md"),
        ]
    )
    vector_store.delete_by_source("faq.txt")

    assert [doc.source for doc in vector_store.list_sources()] == ["guide.md"]
