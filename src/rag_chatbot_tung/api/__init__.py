"""FastAPI application exposing the RAG chatbot over HTTP."""

from rag_chatbot_tung.api.app import create_app

__all__ = ["create_app"]
