# Architecture

## Request flow

```
POST /query {"question": "..."}
        │
        ▼
  RAGOrchestrator.answer()                     orchestrator.py
        │
        ├─► OpenAIEmbedder.embed_query()       embeddings/openai_embedder.py
        │       question → 1536-dim vector
        │
        ├─► QdrantVectorStore.search()         retrieval/vector_search.py
        │       top_k nearest chunks above score_threshold
        │       └─ no hits → return NO_CONTEXT_ANSWER, LLM never called
        │
        ├─► build_rag_messages()               llm_generator/prompts.py
        │       system rules + numbered passages + question
        │       context trimmed to llm.context_token_budget
        │
        └─► OpenAILLM.generate()               llm_generator/openai_llm.py
                │
                ▼
        QueryResponse{answer, sources, model, tokens_used, latency_ms}
```

The browser UI at `/ui` is a static page mounted on this same app; it calls `/query`
exactly like any other client, so nothing above changes when it is used.

## Ingestion flow

```
POST /ingest {"path": "..."}  or  {"url": "..."}
        │
        ▼
  IngestionPipeline                            retrieval/document_retrieval.py
        │
        ├─ load_text / load_pdf / load_url     (pypdf, httpx + BeautifulSoup)
        ├─ clean_text()                        utils/text.py
        ├─ TextSplitter.split[_markdown]()     chunking/splitter.py
        ├─ OpenAIEmbedder.embed_texts()        batched
        ├─ delete_by_source()                  removes the previous version
        └─ upsert()                            Qdrant points with payload metadata
```

Re-ingesting a source is idempotent: point IDs are `uuid5(namespace, "source:index")`
and every existing chunk of that source is deleted before the new ones land, so nothing
is duplicated and stale chunks cannot survive an edit.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `configs.py` | Typed settings; YAML defaults overridden by env/`.env` |
| `logging.py` | One-time root logger setup, `get_logger()` for modules |
| `validate.py` | Pydantic models shared by the API and the pipeline |
| `adaptor/` | `Protocol` interfaces: `EmbeddingProvider`, `VectorStore`, `LLMProvider` |
| `chunking/` | Boundary-aware text splitting, markdown heading awareness |
| `embeddings/` | OpenAI embeddings with batching and rate-limit retry |
| `retrieval/` | Qdrant wrapper + document loaders + ingestion pipeline |
| `llm_generator/` | Chat completion wrapper + grounded prompt construction |
| `orchestrator.py` | Composes the above into `answer` / `ingest` / `health` |
| `api/` | FastAPI app, routes, dependency wiring, error handling |
| `api/static/` | Browser UI served at `/ui` — plain HTML/CSS/JS, no logic, no build step |
| `evaluate/` | Retrieval hit-rate and MRR against a golden Q&A set |

## Why the adaptor layer

`VectorStore` covers `ensure_collection`, `upsert`, `search`, `delete_by_source`,
`list_sources`, `info`, and `health`. `list_sources` walks the collection with `scroll`
rather than a distinct-value call, so it behaves the same against a real server and the
in-memory client the tests use.

`RAGOrchestrator` depends on the three `Protocol`s in `adaptor/protocols.py`, never on
concrete classes. Swapping OpenAI for Ollama, or Qdrant for Pinecone, means writing one
new class — the orchestrator, API, and tests stay untouched. The test suite relies on
this: `tests/conftest.py` injects a hash-based `FakeEmbedder` and a `FakeLLM`, so the
whole suite runs offline.

## Grounding strategy

`SYSTEM_PROMPT` in `llm_generator/prompts.py` restricts the model to the numbered
passages it was given, requires bracket citations, and specifies the exact sentence to
return when the context is insufficient. Two further guards sit outside the prompt:

- `retriever.score_threshold` drops weak matches before they reach the model.
- An empty result set short-circuits — `NO_CONTEXT_ANSWER` is returned without an API call.

## Configuration precedence

```
constructor arguments  >  environment variables  >  .env  >  configs/default.yaml  >  defaults
```

Implemented in `Settings.settings_customise_sources`. Nested fields use `__`, so
`RETRIEVER__TOP_K=5` sets `settings.retriever.top_k`.

## Deployment

`docker-compose.yaml` runs two services: `qdrant` (persisted in the `qdrant_storage`
volume) and `api` (built from the multi-stage `Dockerfile`, non-root, health-checked on
`/health`). Inside the compose network the API reaches the database at `http://qdrant:6333`,
injected via `QDRANT__URL`. `deploy/k8s.yaml` mirrors this with a StatefulSet for Qdrant
and a 2-replica Deployment for the API.
