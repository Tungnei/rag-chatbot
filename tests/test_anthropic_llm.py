"""The Anthropic adapter translates the shared message shape onto the Messages API."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rag_chatbot.configs import LLMSettings
from rag_chatbot.llm_generator import AnthropicLLM


class FakeMessages:
    def __init__(self, response) -> None:
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeAnthropic:
    def __init__(self, response) -> None:
        self.messages = FakeMessages(response)


def make_response(text="grounded answer [1]", stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model="claude-opus-5",
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=120, output_tokens=30),
    )


@pytest.fixture
def messages():
    return [
        {"role": "system", "content": "Answer only from the context."},
        {"role": "user", "content": "Context passages:\n\n[1] ...\n\nQuestion: what?"},
    ]


def test_system_prompt_moves_out_of_the_message_list(messages):
    client = FakeAnthropic(make_response())
    AnthropicLLM(LLMSettings(model="claude-opus-5"), "key", client=client).generate(messages)

    sent = client.messages.calls[0]
    # The Messages API takes the system prompt as its own parameter; leaving it in the
    # list would make it a user turn and quietly drop the grounding rules.
    assert sent["system"] == "Answer only from the context."
    assert [m["role"] for m in sent["messages"]] == ["user"]


def test_temperature_is_never_sent(messages):
    # temperature is removed on current Claude models and returns 400 — the shared
    # LLMSettings still carries it for the OpenAI provider, so it must be dropped here.
    client = FakeAnthropic(make_response())
    settings = LLMSettings(model="claude-opus-5", temperature=0.7)
    AnthropicLLM(settings, "key", client=client).generate(messages)

    assert "temperature" not in client.messages.calls[0]


def test_effort_is_omitted_unless_configured(messages):
    # Not every model accepts effort (Sonnet 4.5 errors on it), so it is opt-in.
    client = FakeAnthropic(make_response())
    AnthropicLLM(LLMSettings(model="claude-sonnet-4-5"), "key", client=client).generate(messages)
    assert "output_config" not in client.messages.calls[0]

    client = FakeAnthropic(make_response())
    settings = LLMSettings(model="claude-opus-5", effort="low")
    AnthropicLLM(settings, "key", client=client).generate(messages)
    assert client.messages.calls[0]["output_config"] == {"effort": "low"}


def test_usage_maps_onto_the_shared_result(messages):
    client = FakeAnthropic(make_response())
    result = AnthropicLLM(LLMSettings(), "key", client=client).generate(messages)

    assert result.text == "grounded answer [1]"
    assert result.model == "claude-opus-5"
    assert result.prompt_tokens == 120
    assert result.completion_tokens == 30
    assert result.total_tokens == 150


def test_base_url_routes_to_a_gateway():
    llm = AnthropicLLM(LLMSettings(base_url="http://localhost:8317"), "key")
    assert str(llm._client.base_url).startswith("http://localhost:8317")


def test_health_lists_models_rather_than_retrieving_one():
    # Gateways that speak the Messages API commonly serve GET /v1/models but 404 on
    # GET /v1/models/{id}; retrieving would report a working LLM as down.
    class FakeModels:
        def __init__(self) -> None:
            self.listed = False

        def list(self):
            self.listed = True
            return SimpleNamespace(data=[])

        def retrieve(self, _model):  # pragma: no cover - must never be called
            raise AssertionError("health must not retrieve a single model")

    client = FakeAnthropic(make_response())
    client.models = FakeModels()

    assert AnthropicLLM(LLMSettings(), "key", client=client).health() is True
    assert client.models.listed


def test_refusal_is_reported_instead_of_an_empty_answer(messages):
    # A declined request returns HTTP 200 with an empty content list; reading content[0]
    # would raise, and returning "" would look like a successful blank answer.
    client = FakeAnthropic(
        SimpleNamespace(
            content=[],
            model="claude-opus-5",
            stop_reason="refusal",
            usage=SimpleNamespace(input_tokens=120, output_tokens=0),
        )
    )
    result = AnthropicLLM(LLMSettings(), "key", client=client).generate(messages)

    assert "từ chối" in result.text
