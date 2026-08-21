"""FastAPI application factory."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from rag_chatbot import __version__
from rag_chatbot.api.routes import router
from rag_chatbot.configs import Settings, get_settings
from rag_chatbot.logging import get_logger, setup_logging
from rag_chatbot.orchestrator import RAGOrchestrator

logger = get_logger(__name__)

# The browser UI ships inside the api package, so it travels with the module rather
# than with the repo layout — Dockerfile already copies src/ wholesale.
STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    settings: Settings | None = None, orchestrator: RAGOrchestrator | None = None
) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.orchestrator = orchestrator or RAGOrchestrator(settings)
        app.state.orchestrator.startup()
        logger.info("RAG chatbot ready (collection=%s)", settings.qdrant.collection_name)
        yield

    app = FastAPI(
        title="RAG Chatbot",
        description="Retrieval Augmented Generation chatbot over your own documents.",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        trace_id = uuid.uuid4().hex[:12]
        logger.exception("unhandled error [%s] on %s", trace_id, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal server error", "trace_id": trace_id},
        )

    app.include_router(router)
    # Mounted last and under a prefix: mounting at "/" would swallow every API route.
    app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    return app
