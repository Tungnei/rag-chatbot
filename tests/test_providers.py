"""Provider selection is an environment setting, not a code change."""

from __future__ import annotations

import sys

import pytest

from rag_chatbot.configs import Settings
from rag_chatbot.embeddings import OpenAIEmbedder
from rag_chatbot.llm_generator import AnthropicLLM, OpenAILLM
from rag_chatbot.providers import build_embedder, build_llm, build_reranker
from rag_chatbot.rerank import NoopReranker


def make_settings(**overrides) -> Settings:
    settings = Settings(openai_api_key="openai-key", anthropic_api_key="anthropic-key")
    for field, value in overrides.items():
        section, _, name = field.partition("__")
        setattr(getattr(settings, section), name, value)
    return settings


def test_llm_defaults_to_openai():
    assert isinstance(build_llm(make_settings()), OpenAILLM)


def test_llm_provider_switches_to_anthropic():
    llm = build_llm(make_settings(llm__provider="anthropic", llm__model="claude-opus-5"))
    assert isinstance(llm, AnthropicLLM)


def test_embedder_stays_on_openai_when_llm_switches():
    # Anthropic serves no embeddings, so the two halves are configured separately and
    # switching the LLM must not drag the embedder along.
    settings = make_settings(llm__provider="anthropic")
    assert isinstance(build_embedder(settings), OpenAIEmbedder)


def test_unknown_provider_is_rejected_at_config_time():
    # Fail while reading settings, not on the first user question.
    with pytest.raises(ValueError):
        Settings(openai_api_key="k", llm={"provider": "gemini"})


def test_missing_key_for_selected_provider_names_the_variable():
    settings = Settings(openai_api_key="k", anthropic_api_key="", llm={"provider": "anthropic"})
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_llm(settings)


def test_build_reranker_defaults_to_noop(settings):
    assert isinstance(build_reranker(settings), NoopReranker)


def test_build_reranker_cross_encoder_without_extra_raises_clearly(settings, monkeypatch):
    """Names the extra to install instead of surfacing a bare ModuleNotFoundError.

    The condition is constructed rather than assumed: on a machine that HAS run
    `uv sync --extra rerank`, letting this reach the real branch would build a
    CrossEncoder and pull ~90MB from HuggingFace in the middle of the suite — exactly
    the offline rule this repo keeps. Blanking the module makes the test deterministic
    on every machine regardless of what is installed.
    """
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    settings.rerank.provider = "cross_encoder"

    with pytest.raises(ValueError) as excinfo:
        build_reranker(settings)

    assert "uv sync --extra rerank" in str(excinfo.value)
