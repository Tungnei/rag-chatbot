FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, without the project itself. This layer is keyed on the lockfile
# alone, so editing src/ no longer reinstalls every dependency — copying the source
# before this step made a one-character change cost a full reinstall.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Then the project itself, which is the only thing a source edit has to redo.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.11-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv ./.venv
COPY --from=builder --chown=app:app /app/src ./src
COPY --chown=app:app configs ./configs

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8000/health').status_code==200 else 1)"

CMD ["rag-chatbot"]


# Separate target, deliberately not a change to `runtime` above: the default image must
# not gain a byte from a feature that ships disabled. Choosing between them is an
# operator decision made at build time, with the size difference visible in
# `docker image ls` rather than discovered later.
FROM builder AS builder-rerank

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra rerank

# Bake the model into the image rather than fetching it on first start. The deciding
# factor is the failure mode, not the size: downloading at runtime turns a visible
# build-time number into a container that "starts slowly" while it pulls ~90MB through
# a network that may block HuggingFace entirely — and it makes air-gapped deployment
# impossible. Same reasoning as failing loudly on a stale collection schema.
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import CrossEncoder; \
    CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', device='cpu')"


FROM python:3.11-slim-bookworm AS runtime-rerank

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/hf \
    RERANK__PROVIDER=cross_encoder

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY --from=builder-rerank --chown=app:app /app/.venv ./.venv
COPY --from=builder-rerank --chown=app:app /app/src ./src
COPY --from=builder-rerank --chown=app:app /opt/hf /opt/hf
COPY --chown=app:app configs ./configs

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8000/health').status_code==200 else 1)"

CMD ["rag-chatbot"]
