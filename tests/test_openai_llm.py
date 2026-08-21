"""Behaviour of the OpenAI-protocol adapter that gateways expose us to."""

from __future__ import annotations

from types import SimpleNamespace

from rag_chatbot.configs import EmbeddingSettings, LLMSettings
from rag_chatbot.embeddings import OpenAIEmbedder
from rag_chatbot.llm_generator import OpenAILLM


class FakeModels:
    def __init__(self) -> None:
        self.listed = False

    def list(self):
        self.listed = True
        return SimpleNamespace(data=[])

    def retrieve(self, _model):  # pragma: no cover - must never be called
        raise AssertionError("health must not retrieve a single model")


def test_health_lists_models_rather_than_retrieving_one():
    # Gateways speaking this protocol commonly 404 on GET /v1/models/{id}, and a model
    # id like "openai/gpt-4o-mini" does not form a valid single-model path at all.
    # Retrieving reported a working LLM as down.
    client = SimpleNamespace(models=FakeModels())
    llm = OpenAILLM(LLMSettings(model="openai/gpt-4o-mini"), "key")
    llm._client = client

    assert llm.health() is True
    assert client.models.listed


def test_base_url_routes_the_llm_to_a_gateway():
    llm = OpenAILLM(LLMSettings(base_url="https://gateway.example/api/v1"), "key")
    assert str(llm._client.base_url).startswith("https://gateway.example/api/v1")


def test_base_url_routes_the_embedder_to_a_gateway():
    # The embedder has its own base_url so the two halves can sit behind different
    # gateways — one may serve embeddings while the other does not.
    embedder = OpenAIEmbedder(EmbeddingSettings(base_url="https://gateway.example/api/v1"), "key")
    assert str(embedder._client.base_url).startswith("https://gateway.example/api/v1")
