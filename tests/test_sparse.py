from __future__ import annotations

import os
import subprocess
import sys
import unicodedata

from rag_chatbot_tung.retrieval.sparse import encode, term_index, tokenize


def test_tokenize_lowercases_and_splits_on_non_word():
    assert tokenize("Qdrant, stores  vectors!") == ["qdrant", "stores", "vectors"]


def test_tokenize_normalises_unicode():
    """Ingest normalises to NFKC; the question does not go through that path.

    For a dense vector an NFC/NFD split only nudges the embedding. For BM25 they are
    two different terms, so the query would silently match nothing.
    """
    nfc = unicodedata.normalize("NFC", "máy học")
    nfd = unicodedata.normalize("NFD", "máy học")

    assert nfc != nfd, "the two forms must actually differ or this test proves nothing"
    assert tokenize(nfc) == tokenize(nfd)


def test_encode_counts_term_frequency():
    vector = encode("a b a")

    weights = dict(zip(vector.indices, vector.values, strict=True))
    assert weights[term_index("a")] == 2.0
    assert weights[term_index("b")] == 1.0


def test_encode_of_empty_text_is_empty():
    # An empty sparse vector must be representable: Qdrant has to accept it rather
    # than raise, or any punctuation-only chunk breaks ingest.
    for text in ("", "   ", "!!! ---"):
        vector = encode(text)
        assert vector.indices == []
        assert vector.values == []


def _run_in_subprocess(code: str, seed: str) -> str:
    result = subprocess.run(
        # sys.executable is the venv interpreter, so the package imports even though
        # the autouse fixture has chdir'd into tmp_path.
        [sys.executable, "-c", code],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_term_index_is_stable_across_processes():
    """R2: an index written by one process must be readable by the next.

    Python randomises str hashing per process, and a single-process test run can
    never catch that — hash() is perfectly stable within one process.
    """
    expected = term_index("máy")
    code = "from rag_chatbot_tung.retrieval.sparse import term_index; print(term_index('máy'))"

    for seed in ("0", "1", "2"):
        assert int(_run_in_subprocess(code, seed)) == expected


def test_plain_hash_would_have_been_caught():
    """Control for the test above — do not delete this.

    The stability test only means something if these subprocesses really do produce
    the variation it claims to detect. If str hashing ever became stable, that test
    would pass against any implementation at all, including a broken one.
    """
    values = {_run_in_subprocess("print(hash('máy'))", seed) for seed in ("0", "1", "2")}

    assert len(values) > 1, (
        "PYTHONHASHSEED no longer varies str hashing — "
        "test_term_index_is_stable_across_processes is now vacuous"
    )
