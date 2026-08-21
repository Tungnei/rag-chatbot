from __future__ import annotations

import pytest
from qdrant_client import QdrantClient, models

from rag_chatbot.adaptor import VectorPoint
from rag_chatbot.retrieval.sparse import encode
from rag_chatbot.retrieval.vector_search import CollectionSchemaError, QdrantVectorStore
from rag_chatbot.validate import SourceType

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


def test_list_sources_survives_unknown_source_type(vector_store):
    # One hand-written or future-version point must not 500 the whole endpoint.
    vector_store.upsert([make_point(point_id(1), 0.5, source_type="html")])
    documents = vector_store.list_sources()
    assert documents[0].source_type is SourceType.TEXT
    assert documents[0].chunks == 1


def test_list_sources_skips_points_without_source(vector_store):
    # A source-less point is unreachable by delete_by_source, so listing it would only
    # offer a delete button that silently does nothing.
    vector_store.upsert(
        [
            make_point(point_id(1), 0.5, source="faq.txt"),
            make_point(point_id(2), 0.4, source=None),
        ]
    )
    assert [doc.source for doc in vector_store.list_sources()] == ["faq.txt"]


def test_list_sources_title_comes_from_the_first_chunk(vector_store):
    # Markdown gives each chunk its enclosing heading, and point ids are uuid5 of
    # "source:index", so id order says nothing about chunk order. Only index 0 holds
    # anything that can be called the document's title.
    vector_store.upsert(
        [
            make_point(point_id(7), 0.5, source="guide.md", index=1, title="Usage"),
            make_point(point_id(3), 0.5, source="guide.md", index=0, title="Guide"),
            make_point(point_id(9), 0.5, source="guide.md", index=2, title="Setup"),
        ]
    )
    assert vector_store.list_sources()[0].title == "Guide"


def test_list_sources_after_delete(vector_store):
    vector_store.upsert(
        [
            make_point(point_id(1), 0.5, source="faq.txt"),
            make_point(point_id(2), 0.4, source="guide.md"),
        ]
    )
    vector_store.delete_by_source("faq.txt")

    assert [doc.source for doc in vector_store.list_sources()] == ["guide.md"]


def test_ensure_collection_creates_named_and_sparse_vectors(vector_store):
    params = vector_store._client.get_collection(vector_store.collection).config.params

    assert isinstance(params.vectors, dict), "hybrid needs NAMED vectors, not a bare VectorParams"
    assert "dense" in params.vectors
    assert params.sparse_vectors is not None
    assert "bm25" in params.sparse_vectors
    # IDF server-side is what keeps BM25 free of any new Python dependency.
    assert params.sparse_vectors["bm25"].modifier is models.Modifier.IDF


def test_ensure_collection_rejects_legacy_unnamed_schema(settings):
    """R3: a pre-hybrid collection must fail loudly at startup, not silently pass.

    Returning early left the old schema in place and every hybrid query then broke
    somewhere far from the cause.
    """
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name=settings.qdrant.collection_name,
        vectors_config=models.VectorParams(size=16, distance=models.Distance.COSINE),
    )
    store = QdrantVectorStore(settings.qdrant, client=client)

    with pytest.raises(CollectionSchemaError) as excinfo:
        store.ensure_collection()

    # An exception that does not name the fix just relocates the confusion.
    assert "migrate_collection.py" in str(excinfo.value)


def test_ensure_collection_rejects_named_without_sparse(settings):
    """Catches a half-finished migration: dense renamed, sparse never added."""
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name=settings.qdrant.collection_name,
        vectors_config={"dense": models.VectorParams(size=16, distance=models.Distance.COSINE)},
    )
    store = QdrantVectorStore(settings.qdrant, client=client)

    with pytest.raises(CollectionSchemaError) as excinfo:
        store.ensure_collection()

    assert "migrate_collection.py" in str(excinfo.value)


def test_ensure_collection_is_idempotent_on_the_new_schema(vector_store):
    vector_store.ensure_collection()
    vector_store.ensure_collection()

    assert vector_store.info().points_count == 0


def test_migration_reingests_only_snapshot_sources(tmp_path):
    """A directory sweep would resurrect every document the user ever deleted.

    DELETE /documents removes the vectors but leaves the uploaded file behind, so
    rebuilding from disk listings silently brings deleted sources back and changes
    the corpus every eval baseline was measured against.
    """
    import scripts.migrate_collection as migrate

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "kept.txt").write_text("kept", encoding="utf-8")
    (uploads / "deleted-but-still-on-disk.txt").write_text("orphan", encoding="utf-8")

    snapshot = {"sources": [{"source": "kept.txt", "chunks": 1}]}

    resolved = [migrate._locate_on_disk(e["source"], [uploads]) for e in snapshot["sources"]]

    assert [p.name for p in resolved] == ["kept.txt"]
    assert (uploads / "deleted-but-still-on-disk.txt").exists()


def _hybrid_store(settings, client=None):
    settings.retriever.hybrid = True
    store = QdrantVectorStore(
        settings.qdrant, client=client or QdrantClient(":memory:"), retriever=settings.retriever
    )
    store.ensure_collection()
    return store


def test_upsert_stores_sparse_vector(settings):
    """Asserts on the stored vector itself, not on a search that could answer from dense.

    An earlier version of this checked only that a search returned the point, and it
    stayed green while upsert silently dropped every sparse vector — the dense branch
    was answering. Hybrid would have been dead on arrival with the suite fully green.
    """
    store = _hybrid_store(settings)
    point = make_point("00000000-0000-0000-0000-000000000010", 0.5)
    point.sparse = encode("qdrant stores vectors")
    store.upsert([point])

    stored = store._client.scroll(store.collection, limit=1, with_vectors=True)[0][0]

    assert "bm25" in stored.vector, "sparse vector was not written to the collection"
    assert stored.vector["bm25"].indices, "sparse vector stored but empty"

    # And the BM25 branch alone can retrieve it.
    probe = encode("qdrant")
    sparse_only = store._client.query_points(
        store.collection,
        query=models.SparseVector(indices=probe.indices, values=probe.values),
        using="bm25",
        limit=5,
    ).points
    assert len(sparse_only) == 1


def test_fusion_without_a_floor_cannot_add_what_dense_missed(settings):
    """The cost of the B2 floor, made explicit.

    With no measured sparse floor a chunk survives only if the thresholded dense
    prefetch already vouched for it, so BM25 can reorder candidates but never widen
    recall. That is the deliberate trade: closing the grounding hole outranks the
    extra recall until a real floor has been measured from real scores.
    """
    store = _hybrid_store(settings)
    dense_match = make_point("00000000-0000-0000-0000-000000000011", 0.5, text="dense side")
    term_match = make_point("00000000-0000-0000-0000-000000000012", -0.5, text="term side")
    term_match.sparse = encode("sparsematchtoken")
    dense_match.sparse = encode("unrelated words here")
    store.upsert([dense_match, term_match])

    fused = store.search([0.5] * 16, top_k=5, score_threshold=0.5, query_text="sparsematchtoken")

    assert [h.text for h in fused] == ["dense side"]


def test_fusion_with_a_measured_floor_admits_a_sparse_only_hit(settings):
    """With a floor set, the BM25 branch can contribute a document of its own."""
    settings.retriever.sparse_score_floor = 0.0
    store = _hybrid_store(settings)
    dense_match = make_point("00000000-0000-0000-0000-000000000011", 0.5, text="dense side")
    term_match = make_point("00000000-0000-0000-0000-000000000012", -0.5, text="term side")
    term_match.sparse = encode("sparsematchtoken")
    dense_match.sparse = encode("unrelated words here")
    store.upsert([dense_match, term_match])

    fused = store.search([0.5] * 16, top_k=5, score_threshold=0.5, query_text="sparsematchtoken")
    dense_only = store.search([0.5] * 16, top_k=5, score_threshold=0.5)

    assert len(dense_only) == 1, "dense alone must not reach the term-only point"
    assert {h.text for h in fused} == {"dense side", "term side"}


def test_hybrid_off_matches_dense_only(settings):
    """Evidence the switch really switches off."""
    settings.retriever.hybrid = False
    store = QdrantVectorStore(
        settings.qdrant, client=QdrantClient(":memory:"), retriever=settings.retriever
    )
    store.ensure_collection()
    point = make_point("00000000-0000-0000-0000-000000000013", 0.5)
    point.sparse = encode("sparsematchtoken")
    store.upsert([point])

    with_text = store.search([0.5] * 16, top_k=5, query_text="sparsematchtoken")
    without_text = store.search([0.5] * 16, top_k=5)

    assert [(h.source, h.score) for h in with_text] == [(h.source, h.score) for h in without_text]


def test_points_without_sparse_survive_hybrid_search(settings):
    """Points written before this phase carry no sparse vector; they must not break."""
    store = _hybrid_store(settings)
    legacy = make_point("00000000-0000-0000-0000-000000000014", 0.5, text="legacy point")
    store.upsert([legacy])

    hits = store.search([0.5] * 16, top_k=5, query_text="anything at all")

    assert [h.text for h in hits] == ["legacy point"]


def test_score_threshold_applies_inside_the_dense_prefetch(settings):
    """R4: an RRF score is not a cosine, so the cosine threshold cannot apply after fusion.

    Asserted against the Prefetch objects handed to the client rather than against a
    constructed fused score — the plan's own instruction, since guessing which fused
    value lands under 0.3 would be a test built on speculation.
    """
    store = _hybrid_store(settings)
    calls = []
    original = store._client.query_points

    def spy(**kwargs):
        # Recorded per call, not merged: the hybrid path issues several queries and
        # merging them would blend the fusion call's arguments with the others'.
        calls.append(kwargs)
        return original(**kwargs)

    store._client.query_points = spy
    store.search([0.5] * 16, top_k=5, score_threshold=0.3, query_text="something")

    fusion_call = [c for c in calls if "prefetch" in c][0]
    captured = fusion_call
    prefetch = fusion_call["prefetch"]
    dense = [p for p in prefetch if p.using == "dense"][0]
    sparse = [p for p in prefetch if p.using == "bm25"][0]

    assert dense.score_threshold == 0.3, "threshold belongs inside the dense prefetch"
    assert sparse.score_threshold is None, "no measured threshold exists for BM25 scores"
    assert captured.get("score_threshold") is None, "must not filter on fused scores"


def test_offtopic_query_still_abstains_under_hybrid(settings):
    """B2: BM25 matches on a single shared token, so a stopword can drag in junk.

    Without a post-fusion floor an off-topic question returns unrelated passages and
    the orchestrator's empty-result guard — one of the system's two anti-fabrication
    layers — silently stops firing.
    """
    store = _hybrid_store(settings)
    doc = make_point("00000000-0000-0000-0000-000000000015", 0.5, text="về chính sách nghỉ phép")
    doc.sparse = encode("về chính sách nghỉ phép của công ty")
    store.upsert([doc])

    # Shares only the stopword "về" and is nowhere near it in dense space.
    hits = store.search([-0.9] * 16, top_k=5, score_threshold=0.3, query_text="về giá vé máy bay")

    assert hits == [], "off-topic query must not be rescued into the context by BM25"
