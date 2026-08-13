"""Provider selection is an environment setting, not a code change."""

from __future__ import annotations

import pytest

from rag_chatbot_tung.configs import Settings
from rag_chatbot_tung.embeddings import OpenAIEmbedder
from rag_chatbot_tung.llm_generator import AnthropicLLM, OpenAILLM
from rag_chatbot_tung.providers import build_embedder, build_llm


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
