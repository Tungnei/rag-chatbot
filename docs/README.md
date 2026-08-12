# Documentation

- **[SETUP.md](./SETUP.md)** — install, configure, run, troubleshoot
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — request and ingestion flows, design decisions
- **[PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)** — what lives where, key types
- **[QUICK_REFERENCE.md](./QUICK_REFERENCE.md)** — commands, API calls, tuning table

## What this project is

A question-answering service over your own documents. Text, Markdown, and PDF files (or
web pages) are split into chunks, embedded with OpenAI, and stored in Qdrant. At query
time the most similar chunks are retrieved and handed to a chat model that is instructed
to answer only from them, with bracket citations — and to say so plainly when the answer
is not there.

## Stack

| Concern | Choice |
|---|---|
| HTTP API | FastAPI + uvicorn |
| Vector store | Qdrant (self-hosted via docker compose) |
| Embeddings | OpenAI `text-embedding-3-small` |
| Generation | OpenAI `gpt-4o-mini` |
| Config | pydantic-settings, YAML + env |
| Packaging | uv, Python 3.11 |

The OpenAI and Qdrant integrations sit behind `Protocol` interfaces in `adaptor/`, so
either can be replaced without touching the orchestrator or the API.
