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

Interactive API docs: <http://localhost:8000/docs>

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
| DELETE | `/documents?source=…` | Remove every chunk of one source |

Supported formats: `.txt`, `.md`, `.pdf`, plus any web page by URL.

## Configuration

`configs/default.yaml` holds the defaults; environment variables in `.env` override them.
Nested settings use a double underscore, e.g. `RETRIEVER__TOP_K=5`.

Precedence: environment > `.env` > `configs/default.yaml` > built-in defaults.

## Development commands

```bash
uv run pytest                    # 45 tests, no network calls
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
