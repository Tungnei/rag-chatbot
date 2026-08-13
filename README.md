# RAG Chatbot

A Retrieval Augmented Generation chatbot that answers questions from your own documents.
FastAPI for the HTTP layer, Qdrant for vector search, OpenAI for embeddings and generation.

## Quick start

```bash
cp .env.example .env          # then set OPENAI_API_KEY
docker compose up --build -d

curl localhost:8000/health
curl -X POST localhost:8000/ingest \
     -H 'Content-Type: application/json' \
     -d '{"path": "sample_faq.txt"}'
curl -X POST localhost:8000/query \
     -H 'Content-Type: application/json' \
     -d '{"question": "What embedding model is used by default?"}'
```

Browser UI: <http://localhost:8000/ui> — ask questions and read the sources side by side.
Document management: <http://localhost:8000/ui/admin>.

Interactive API docs: <http://localhost:8000/docs>

> Neither the UI nor the API has any authentication, and CORS is wide open. Keep this on
> localhost. Exposing port 8000 lets anyone burn your OpenAI credit or wipe the index.

## Local development

```bash
uv sync                                       # Python 3.11 + dependencies
docker run -p 6333:6333 qdrant/qdrant         # vector store
uv run python scripts/ingest.py               # index data/documents/
uv run rag-chatbot-tung                       # start the API
```

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Qdrant and OpenAI connectivity |
| POST | `/query` | Ask a question, get a grounded answer with sources |
| POST | `/ingest` | Index a file under `data/documents/` or a URL |
| POST | `/ingest/upload` | Upload and index a file directly |
| GET | `/collections` | Number of indexed chunks |
| GET | `/documents` | Every indexed source with its chunk count |
| DELETE | `/documents?source=…` | Remove every chunk of one source |

The browser UI is served by the same app: `/ui` for chat, `/ui/admin` for documents.

Supported formats: `.txt`, `.md`, `.pdf`, plus any web page by URL.

## Configuration

`configs/default.yaml` holds the defaults; environment variables in `.env` override them.
Nested settings use a double underscore, e.g. `RETRIEVER__TOP_K=5`.

### Choosing an LLM provider

```bash
LLM__PROVIDER=anthropic
LLM__MODEL=claude-opus-5
ANTHROPIC_API_KEY=sk-ant-...
```

That is the whole switch — the orchestrator depends on the `LLMProvider` protocol, so no
code changes. Two things do not move with it:

- **Embeddings stay on OpenAI.** Anthropic has no embeddings API, so `OPENAI_API_KEY` is
  required whichever LLM you pick. This is deliberate: the embedder and the LLM are
  configured separately, because changing the embedding model invalidates every vector
  already stored.
- **`LLM__TEMPERATURE` is ignored on Anthropic.** Current Claude models reject
  `temperature` with a 400; use `LLM__EFFORT` (`low`…`max`) instead, where the model
  supports it. Also give `LLM__MAX_TOKENS` more headroom — on Claude it covers the
  model's thinking as well as the answer.

Precedence: environment > `.env` > `configs/default.yaml` > built-in defaults.

## Development commands

```bash
uv run pytest                    # 60 tests, no network calls
uv run ruff check src tests
uv run black src tests
uv run mypy src
uv run python scripts/run_eval.py   # retrieval hit-rate and MRR
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the pieces fit together
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) — what lives where
- [docs/SETUP.md](docs/SETUP.md) — installation and troubleshooting
- [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) — commands and snippets
