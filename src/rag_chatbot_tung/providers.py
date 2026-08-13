"""Builds the concrete provider implementations named in the settings.

The orchestrator depends only on the `adaptor/` Protocols, so switching providers is a
configuration change. This module is the one place that knows which class each
`provider` value maps to, and which API key that provider needs.
"""

from __future__ import annotations

from rag_chatbot_tung.adaptor import EmbeddingProvider, LLMProvider
from rag_chatbot_tung.configs import Settings
from rag_chatbot_tung.embeddings import OpenAIEmbedder
from rag_chatbot_tung.llm_generator import AnthropicLLM, OpenAILLM

_LLM_KEY_FIELDS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def _require(key: str, provider: str) -> str:
    if not key:
        # Name the variable: "authentication error" from the provider three calls later
        # is a much worse way to learn the key was never set.
        raise ValueError(
            f"{_LLM_KEY_FIELDS[provider]} is required when the provider is '{provider}'"
        )
    return key


def build_llm(settings: Settings) -> LLMProvider:
    if settings.llm.provider == "anthropic":
        return AnthropicLLM(settings.llm, _require(settings.anthropic_api_key, "anthropic"))
    return OpenAILLM(settings.llm, _require(settings.openai_api_key, "openai"))


def build_embedder(settings: Settings) -> EmbeddingProvider:
    """Always OpenAI today — Anthropic serves no embeddings API.

    Kept as a factory anyway so the LLM and the embedder switch independently: moving
    generation to Claude must not silently change the embedding model, which would
    invalidate every vector already in the collection.
    """
    return OpenAIEmbedder(settings.embeddings, _require(settings.openai_api_key, "openai"))
