# RAG Chatbot User Guide

This guide explains how to operate the RAG chatbot from ingestion to querying.

## Getting Started

### Prerequisites

You need Python 3.11 or newer, the `uv` package manager, a running Qdrant instance,
and a valid OpenAI API key exported as `OPENAI_API_KEY`.

### Installation

Run `uv sync` in the project root. This creates a virtual environment and installs all
dependencies pinned in `uv.lock`.

## Ingesting Documents

### From the file system

Place your files in `data/documents/` and run the ingestion script:
`uv run python scripts/ingest.py`. The script walks the directory, loads every supported
file, splits it into chunks, embeds each chunk, and upserts the vectors into Qdrant.

### From a URL

Send a POST request to `/ingest` with a JSON body containing a `url` field. The loader
fetches the page, strips scripts, styles, and navigation elements, and keeps the readable
text content only.

## Querying

Send a POST request to `/query` with a `question` field. The orchestrator embeds the
question, searches Qdrant for the most similar chunks, builds a prompt containing those
chunks as context, and asks the language model to answer using only that context.

### Understanding the response

The response contains the generated `answer`, a list of `sources` with the originating
file name and a short snippet, the `model` used, total `tokens_used`, and the request
`latency_ms`.

## Tuning Retrieval Quality

### Chunk size

Smaller chunks give more precise retrieval but may lose surrounding context. Larger chunks
preserve context but dilute the embedding signal. The default is 1000 characters with an
overlap of 100 characters.

### Top-K and score threshold

Increasing `top_k` gives the model more context at the cost of more tokens. The
`score_threshold` filters out weakly matching chunks; raising it reduces noise but risks
returning no results at all.

## Troubleshooting

If `/health` reports `qdrant: false`, verify that the Qdrant container is running and that
`QDRANT__URL` points at the right host. Inside docker compose the host is `qdrant`, not
`localhost`.

If queries return "not found in the indexed documents", confirm that ingestion actually
inserted points by calling `GET /collections`.
