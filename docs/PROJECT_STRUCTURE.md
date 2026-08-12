# Project Structure

```
rag-chatbot-tung/
├── src/rag_chatbot_tung/
│   ├── __init__.py                     # __version__ and main() → uvicorn
│   ├── configs.py                      # Settings, get_settings()
│   ├── logging.py                      # setup_logging(), get_logger()
│   ├── validate.py                     # all Pydantic models
│   ├── orchestrator.py                 # RAGOrchestrator
│   ├── adaptor/
│   │   └── protocols.py                # EmbeddingProvider, VectorStore, LLMProvider
│   ├── chunking/
│   │   └── splitter.py                 # TextSplitter
│   ├── embeddings/
│   │   └── openai_embedder.py          # OpenAIEmbedder
│   ├── retrieval/
│   │   ├── vector_search.py            # QdrantVectorStore
│   │   └── document_retrieval.py       # loaders + IngestionPipeline
│   ├── llm_generator/
│   │   ├── openai_llm.py               # OpenAILLM
│   │   └── prompts.py                  # SYSTEM_PROMPT, build_rag_messages()
│   ├── evaluate/
│   │   └── metrics.py                  # hit-rate, MRR
│   ├── core/__init__.py                # re-exports RAGOrchestrator, Settings
│   ├── utils/
│   │   ├── text.py                     # clean_text, normalize_whitespace
│   │   └── tokens.py                   # count_tokens, truncate_to_tokens
│   └── api/
│       ├── app.py                      # create_app()
│       ├── routes.py                   # endpoints
│       └── dependencies.py             # get_orchestrator()
├── scripts/
│   ├── ingest.py                       # bulk-index data/documents/
│   └── run_eval.py                     # retrieval quality report
├── tests/                              # 45 tests, fully offline
├── data/
│   ├── documents/                      # source documents (2 samples included)
│   ├── uploads/                        # files received via /ingest/upload
│   └── eval/qa.jsonl                   # golden Q&A set
├── configs/default.yaml                # default settings
├── docs/                               # this documentation
├── deploy/k8s.yaml                     # Kubernetes manifests
├── Dockerfile                          # multi-stage uv build
├── docker-compose.yaml                 # api + qdrant
└── pyproject.toml                      # dependencies, ruff/black/mypy/pytest config
```

## Key types

Defined in `validate.py` and shared by every layer:

| Type | Purpose |
|---|---|
| `SourceType` | `text` / `markdown` / `pdf` / `url` |
| `Chunk` | A split piece of a document, before embedding |
| `RetrievedChunk` | A search hit: chunk plus similarity score |
| `Source` | Citation shown in an API response |
| `GenerationResult` | LLM output plus token usage |
| `QueryRequest` / `QueryResponse` | `/query` contract |
| `IngestRequest` / `IngestResponse` | `/ingest` contract |
| `CollectionInfo`, `HealthResponse` | `/collections`, `/health` |

`IngestRequest` validates that exactly one of `path` or `url` is supplied — supplying
both or neither returns HTTP 422.

## Where to make common changes

| Goal | File |
|---|---|
| Change how documents are split | `chunking/splitter.py` |
| Support a new file format | `retrieval/document_retrieval.py` (`_EXTENSION_TYPES`) |
| Change the answer style or citation rules | `llm_generator/prompts.py` |
| Add an API endpoint | `api/routes.py` |
| Add a setting | `configs.py` + `configs/default.yaml` |
| Swap LLM or vector store provider | New class implementing the matching `adaptor/` Protocol |
