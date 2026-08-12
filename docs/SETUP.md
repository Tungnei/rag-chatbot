# Setup

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Docker (for Qdrant, and for the containerised deployment)
- An OpenAI API key

## Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env      # add this line to ~/.zshrc to make it permanent
uv --version
```

## Option A — everything in Docker

```bash
cp .env.example .env      # set OPENAI_API_KEY
docker compose up --build -d
docker compose logs -f api
```

The API is on port 8000, Qdrant on 6333. Documents in `./data/documents` are mounted into
the container, so `{"path": "sample_faq.txt"}` works immediately.

## Option B — local Python, Qdrant in Docker

```bash
uv sync
docker run -d -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant

cp .env.example .env      # set OPENAI_API_KEY
uv run python scripts/ingest.py
uv run rag-chatbot-tung
```

## Environment variables

Nested settings use a double underscore. Everything has a default except the API key.

```env
OPENAI_API_KEY=sk-...

QDRANT__URL=http://localhost:6333
QDRANT__API_KEY=
QDRANT__COLLECTION_NAME=documents

LLM__MODEL=gpt-4o-mini
LLM__TEMPERATURE=0.7
LLM__MAX_TOKENS=2000

EMBEDDINGS__MODEL=text-embedding-3-small

RETRIEVER__TOP_K=3
RETRIEVER__SCORE_THRESHOLD=0.3

API__HOST=0.0.0.0
API__PORT=8000
LOG_LEVEL=INFO
```

Changing `EMBEDDINGS__MODEL` also requires changing `QDRANT__VECTOR_SIZE`
(`text-embedding-3-small` → 1536, `text-embedding-3-large` → 3072) **and** recreating the
collection, because Qdrant fixes the vector size at creation time.

## Adding documents

Drop `.txt`, `.md`, or `.pdf` files into `data/documents/`, then either:

```bash
uv run python scripts/ingest.py                  # index the whole directory
uv run python scripts/ingest.py --url https://example.com/page
```

or call the API:

```bash
curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
     -d '{"path": "my-notes.md"}'
curl -X POST localhost:8000/ingest/upload -F 'file=@/path/to/report.pdf'
```

## Verifying the install

```bash
uv run pytest                          # 45 tests, no network access needed
curl localhost:8000/health             # expects qdrant:true, openai:true
curl localhost:8000/collections        # expects points_count > 0 after ingesting
```

## Troubleshooting

**`zsh: command not found: uv`** — run `source $HOME/.local/bin/env`, and add that line to
`~/.zshrc` so it persists.

**`/health` reports `qdrant: false`** — Qdrant is unreachable. Check `docker ps`, and note
that inside docker compose the host is `qdrant`, not `localhost`.

**`/health` reports `openai: false`** — the API key is missing, invalid, or the configured
model is not available to your account.

**Queries always return "could not find anything relevant"** — either nothing is indexed
(check `GET /collections`) or `RETRIEVER__SCORE_THRESHOLD` is too high; try `0.1`.

**Vector dimension errors on ingest** — the collection was created with a different
embedding model. Delete the collection or the `qdrant_storage` volume and re-ingest.

**Import errors after pulling changes** — run `uv sync` to install new dependencies.
