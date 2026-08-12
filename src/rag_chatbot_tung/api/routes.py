"""HTTP routes for querying and managing the document index."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from rag_chatbot_tung import __version__
from rag_chatbot_tung.api.dependencies import get_orchestrator
from rag_chatbot_tung.logging import get_logger
from rag_chatbot_tung.orchestrator import RAGOrchestrator
from rag_chatbot_tung.retrieval import UnsupportedFormatError
from rag_chatbot_tung.validate import (
    CollectionInfo,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)

logger = get_logger(__name__)
router = APIRouter()

Orchestrator = Annotated[RAGOrchestrator, Depends(get_orchestrator)]


@router.get("/health", response_model=HealthResponse)
def health(orchestrator: Orchestrator) -> HealthResponse:
    return orchestrator.health(version=__version__)


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, orchestrator: Orchestrator) -> QueryResponse:
    return orchestrator.answer(request)


@router.post("/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest, orchestrator: Orchestrator) -> IngestResponse:
    try:
        return orchestrator.ingest(request)
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except UnsupportedFormatError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc


@router.post("/ingest/upload", response_model=IngestResponse)
async def ingest_upload(
    orchestrator: Orchestrator,
    file: Annotated[UploadFile, File()],
) -> IngestResponse:
    if not file.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing filename")

    upload_dir = orchestrator.settings.storage.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Keep only the basename so a crafted filename cannot escape the upload directory.
    target = upload_dir / Path(file.filename).name
    target.write_bytes(await file.read())

    try:
        count = orchestrator.pipeline.ingest_file(target)
    except UnsupportedFormatError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    return IngestResponse(source=target.name, chunks_indexed=count)


@router.get("/collections", response_model=CollectionInfo)
def collection_info(orchestrator: Orchestrator) -> CollectionInfo:
    return orchestrator.collection_info()


@router.delete("/documents", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    orchestrator: Orchestrator, source: Annotated[str, Query(min_length=1)]
) -> None:
    orchestrator.delete_source(source)
