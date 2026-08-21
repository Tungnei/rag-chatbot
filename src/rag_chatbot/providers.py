"""Builds the concrete provider implementations named in the settings.

The orchestrator depends only on the `adaptor/` Protocols, so switching providers is a
configuration change. This module is the one place that knows which class each
`provider` value maps to, and which API key that provider needs.
"""

from __future__ import annotations

from rag_chatbot.adaptor import EmbeddingProvider, LLMProvider, Reranker
from rag_chatbot.configs import Settings
from rag_chatbot.embeddings import OpenAIEmbedder
from rag_chatbot.llm_generator import AnthropicLLM, OpenAILLM
from rag_chatbot.rerank import NoopReranker

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


def build_reranker(settings: Settings) -> Reranker:
    """Noop unless the operator opted into the heavy path.

    The cross-encoder import stays inside this branch so the default install never
    touches torch, and a missing extra is reported by name rather than as a bare
    ModuleNotFoundError three frames deeper.
    """
    if settings.rerank.provider != "cross_encoder":
        return NoopReranker()

    from rag_chatbot.rerank.cross_encoder import CrossEncoderReranker

    try:
        # Construction is what triggers the sentence_transformers import — the module
        # above imports fine without it, since the heavy import is deliberately inside
        # __init__ to keep `import rag_chatbot.rerank` free of torch.
        return CrossEncoderReranker(settings.rerank)
    except ImportError as exc:
        raise ValueError(
            "rerank.provider is 'cross_encoder' but sentence-transformers is not "
            "installed. Install the extra: uv sync --extra rerank"
        ) from exc
