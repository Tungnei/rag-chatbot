"""Term-frequency encoding for the BM25 half of hybrid retrieval.

Qdrant applies the IDF modifier server-side, so this only has to ship raw term
frequencies. That is what keeps BM25 free of any new dependency — no fastembed, no
onnxruntime, roughly forty lines of standard library instead.
"""

from __future__ import annotations

import re
import unicodedata
import zlib
from collections import Counter

from rag_chatbot.adaptor import SparseVector

_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Split into lowercase word tokens, normalising Unicode first.

    Ingested text is NFKC-normalised by `clean_text`, but the question is not — it goes
    straight from the request into the query path. For a dense vector that asymmetry
    only nudges the embedding; for BM25 an NFC "máy" and an NFD "máy" are different
    terms outright and the query silently matches nothing. Normalising here fixes both
    directions at once, because ingest and query both arrive through `encode`.

    Known limitation for Vietnamese: syllables split on whitespace, so "máy học" becomes
    two unigrams and the compound meaning is lost. Accepted deliberately — BM25 is only
    half of the fusion and the dense half still carries the semantics. Solving it with a
    word-segmentation library would forfeit exactly the dependency-free property above.
    """
    return _TOKEN.findall(unicodedata.normalize("NFKC", text).lower())


def term_index(term: str) -> int:
    """Map a term to a stable u32 index.

    zlib.crc32 rather than hash(): Python randomises str hashing per process, so an
    index written today would be unreadable tomorrow — and no single-process test can
    catch it, because hash() is perfectly stable within one process.

    Collisions: crc32 spans 2^32, so ~10^5 distinct terms give roughly one expected
    collision. Two terms sharing a dimension adds mild ranking noise; it does not
    corrupt the index. Hashing wider and truncating would land on the same problem,
    since Qdrant takes u32 indices.
    """
    return zlib.crc32(term.encode("utf-8"))


def encode(text: str) -> SparseVector:
    """Raw term frequencies; Qdrant's IDF modifier supplies the rest."""
    counts = Counter(tokenize(text))
    indices = [term_index(term) for term in counts]
    values = [float(count) for count in counts.values()]
    return SparseVector(indices=indices, values=values)
