"""Shared request-scoped dependencies."""

from __future__ import annotations

from fastapi import Request

from rag_chatbot.orchestrator import RAGOrchestrator


def get_orchestrator(request: Request) -> RAGOrchestrator:
    return request.app.state.orchestrator
