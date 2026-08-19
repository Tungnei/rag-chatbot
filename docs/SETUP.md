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
uv run pytest                          # 60 tests, no network access needed
curl localhost:8000/health             # expects qdrant:true, openai:true
curl localhost:8000/collections        # expects points_count > 0 after ingesting
curl -sL -o /dev/null -w '%{http_code}\n' localhost:8000/ui   # expects 200
```

`-L` is not optional on `/ui`: the static mount answers the bare path with a 307 to
`/ui/`, so plain `curl localhost:8000/ui` prints 307 and looks broken when it is not.

## Optional: cross-encoder reranking

Off by default, and deliberately not part of a normal install — it pulls in torch.

```bash
uv sync --extra rerank            # adds sentence-transformers + CPU-only torch
RERANK__PROVIDER=cross_encoder uv run rag-chatbot-tung
```

torch is pinned to the CPU wheel index; without that pin it drags in the entire CUDA
toolkit, which is several gigabytes of GPU runtime for a model this project runs on CPU.

For containers, build the separate target rather than the default one:

```bash
docker build --target runtime-rerank -t rag-chatbot-tung:rerank .
```

The default `runtime` target is untouched by any of this, so an operator who does not
want the dependency does not pay for it. The model is baked into the image at build
time rather than fetched on first start: that turns a container which mysteriously
"starts slowly" while pulling ~90MB into a size visible in `docker image ls`, and it
keeps air-gapped deployment possible.

Measured before enabling it (DEC-10): on the current eval set the cross-encoder scored
*worse* than fusion alone while costing ~1GB and roughly doubling retrieval latency.
Read DEC-10 before turning it on.

## Upgrading an existing index to the hybrid schema

Collections created before hybrid retrieval store a single **unnamed** vector. Hybrid
needs **named** ones (`dense` plus a sparse `bm25`), and Qdrant will not mix the two.
There is no in-place conversion, so the collection is rebuilt from the files on disk.

Run this **once per Qdrant instance**, not once per checkout — each environment has its
own collection, and migrating your laptop does nothing for staging.

```bash
uv run python scripts/migrate_collection.py             # dry run, changes nothing
uv run python scripts/migrate_collection.py --yes       # actually rebuild
```

The dry run prints how many sources are indexed and how many can be restored from
`data/documents/` and `data/uploads/`. **If any source is missing from disk the script
aborts** rather than destroying it — documents ingested by URL have no local copy, and
those are gone for good if you continue with `--allow-missing`.

Only the sources recorded in the snapshot are re-ingested. That is deliberate: deleting
a document removes its vectors but leaves the uploaded file behind, so rebuilding from a
directory listing would quietly resurrect everything you ever deleted.

If a run is interrupted, run the same command again. It detects the unfinished run and
resumes against the **original** snapshot instead of re-reading the half-rebuilt
collection, and it exits non-zero if the result does not match that baseline.

## Troubleshooting

### The app will not start after upgrading

```
CollectionSchemaError: collection 'documents' uses the pre-hybrid unnamed vector schema.
Run: uv run python scripts/migrate_collection.py --yes
```

This is the schema check refusing to serve a collection it cannot query correctly, and
it fires during startup — so `/ui` is down too, not just the API. Run the migration
above. Running with a mismatched schema would be worse than not starting: queries would
fail far away from the cause.


**`zsh: command not found: uv`** — run `source $HOME/.local/bin/env`, and add that line to
`~/.zshrc` so it persists.

**`/health` reports `qdrant: false`** — Qdrant is unreachable. Check `docker ps`, and note
that inside docker compose the host is `qdrant`, not `localhost`.

**`/ui` does not load at all** — this is expected when Qdrant was already down at
startup, and it is not a UI bug. `create_app` calls `ensure_collection()` during
lifespan, so an unreachable Qdrant stops uvicorn from starting: there is no server left
to serve the page, and the UI cannot report the failure because it never loads. Check
`docker compose ps` first, then `curl localhost:8000/health`. Start Qdrant and restart
the API.

**`/health` reports `openai: false`** — the API key is missing, invalid, or the configured
model is not available to your account.

**Queries always return "could not find anything relevant"** — either nothing is indexed
(check `GET /collections`) or `RETRIEVER__SCORE_THRESHOLD` is too high; try `0.1`.

**Vector dimension errors on ingest** — the collection was created with a different
embedding model. Delete the collection or the `qdrant_storage` volume and re-ingest.

**Import errors after pulling changes** — run `uv sync` to install new dependencies.
