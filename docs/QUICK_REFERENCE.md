# Quick Reference

## Browser UI

| URL | Page |
|---|---|
| <http://localhost:8000/ui> | Chat: question on the left, sources on the right, `[1]` jumps to a source |
| <http://localhost:8000/ui/admin> | Upload, list indexed sources, delete a source |

No authentication on either page — localhost only.

## Commands

```bash
uv sync                                # install dependencies
uv run rag-chatbot                # start the API
uv run python scripts/ingest.py        # index data/documents/
uv run python scripts/run_eval.py      # retrieval hit-rate and MRR
uv run pytest -q                       # tests (offline)
uv run ruff check src tests            # lint
uv run black src tests                 # format
uv run mypy src                        # type check
docker compose up --build -d           # api + qdrant
docker compose down -v                 # stop and wipe the vector store
```

## API calls

```bash
curl localhost:8000/health
curl localhost:8000/collections
curl localhost:8000/documents

# The UI redirects /ui to /ui/, so -L is required or curl reports 307.
curl -sL -o /dev/null -w '%{http_code}\n' localhost:8000/ui

curl -X POST localhost:8000/query -H 'Content-Type: application/json' \
     -d '{"question": "What embedding model is used?", "top_k": 5}'

# Multi-turn: client replays history, server stays stateless. Last 3 exchanges kept,
# capped by llm.history_token_budget so history cannot crowd out the passages.
curl -X POST localhost:8000/query -H 'Content-Type: application/json' \
     -d '{"question": "And how many dimensions?",
          "history": [{"role": "user", "content": "Which embedding model?"},
                      {"role": "assistant", "content": "text-embedding-3-small."}]}'

curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
     -d '{"path": "sample_faq.txt"}'

curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
     -d '{"url": "https://example.com/docs"}'

curl -X POST localhost:8000/ingest/upload -F 'file=@report.pdf'

curl -X DELETE 'localhost:8000/documents?source=sample_faq.txt'
```

## Python usage

```python
from rag_chatbot.core import RAGOrchestrator, get_settings
from rag_chatbot.validate import IngestRequest, QueryRequest

orchestrator = RAGOrchestrator(get_settings())
orchestrator.startup()

orchestrator.ingest(IngestRequest(path="sample_faq.txt"))
response = orchestrator.answer(QueryRequest(question="Where are vectors stored?"))

print(response.answer)
for source in response.sources:
    print(f"  {source.source} ({source.score:.3f})")
```

## Settings cheat sheet

| Env var | Default | Effect |
|---|---|---|
| `RETRIEVER__TOP_K` | 3 | Chunks fed to the model |
| `RETRIEVER__SCORE_THRESHOLD` | 0.3 | Below this, a chunk is discarded |
| `CHUNKING__CHUNK_SIZE` | 1000 | Max characters per chunk |
| `CHUNKING__CHUNK_OVERLAP` | 100 | Characters repeated between chunks |
| `LLM__MODEL` | gpt-4o-mini | Chat model |
| `LLM__TEMPERATURE` | 0.7 | Lower = more literal answers |
| `LLM__CONTEXT_TOKEN_BUDGET` | 6000 | Context is trimmed to fit this |
| `EMBEDDINGS__MODEL` | text-embedding-3-small | Must match `QDRANT__VECTOR_SIZE` |
| `QDRANT__VECTOR_SIZE` | 1536 | Fixed when the collection is created |

## Tuning retrieval

| Symptom | Try |
|---|---|
| Answers miss details in the docs | Raise `RETRIEVER__TOP_K`, lower `CHUNKING__CHUNK_SIZE` |
| Answers pull in unrelated content | Raise `RETRIEVER__SCORE_THRESHOLD` |
| "Could not find anything relevant" too often | Lower `RETRIEVER__SCORE_THRESHOLD` to 0.1 |
| Answers are too creative | Lower `LLM__TEMPERATURE` to 0.1 |

Measure changes instead of guessing: add cases to `data/eval/qa.jsonl`, then compare
`uv run python scripts/run_eval.py` before and after.

## Testing fakes

`tests/conftest.py` provides `FakeEmbedder` (SHA-256-derived vectors) and `FakeLLM`, plus
an in-memory Qdrant via `QdrantClient(":memory:")`. Inject them through the
`RAGOrchestrator` constructor — no test touches the network.

## Retrieval layers and their switches

Three layers ship behind switches so turning one on or off is one variable, not a
revert. DEC-10 records the measured defaults — read it before flipping any of them.

```bash
RETRIEVER__HYBRID=true            # dense + BM25 with RRF fusion (ON by default)
RERANK__PROVIDER=cross_encoder    # needs `uv sync --extra rerank` (OFF: noop)
METADATA_ADJUST__ENABLED=true     # per-source cap, merge, title boost (OFF)
```

The chain of limits, in the order a query passes them:

| Setting | Default | Controls |
|---|---|---|
| `retriever.dense_prefetch_limit` | 30 | candidates from the dense branch |
| `retriever.sparse_prefetch_limit` | 30 | candidates from the BM25 branch |
| `retriever.fusion_limit` | 30 | survivors of fusion, handed to the reranker |
| `rerank.top_n` | 10 | survivors of reranking |
| `retriever.top_k` | 5 | passages the LLM finally receives |

## Measuring a change

```bash
# One configuration, written out so runs can be compared case by case.
uv run python scripts/run_eval.py --top-k 5 --out data/eval/mine.json

# Same thing against a previous run: prints which cases flipped, not just the totals.
uv run python scripts/run_eval.py --top-k 5 --baseline data/eval/mine.json

# The multi-turn A/B: same cases, pronoun phrasing vs self-contained.
uv run python scripts/run_eval.py --cases data/eval/qa_multiturn.jsonl --selfcontained
```

Always pass `--top-k` explicitly when comparing runs. Hit-rate@5 is at least
hit-rate@3 by definition, so a forgotten flag reads as an improvement that no layer
produced.

## Upgrading an existing collection

```bash
uv run python scripts/migrate_collection.py            # dry run, changes nothing
uv run python scripts/migrate_collection.py --yes      # rebuild with the hybrid schema
```
