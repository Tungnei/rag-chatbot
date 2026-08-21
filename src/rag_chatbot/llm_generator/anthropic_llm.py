"""Anthropic-backed implementation of LLMProvider."""

from __future__ import annotations

from typing import Any

from anthropic import Anthropic

from rag_chatbot.configs import LLMSettings
from rag_chatbot.logging import get_logger
from rag_chatbot.validate import GenerationResult

logger = get_logger(__name__)

REFUSAL_ANSWER = "Mô hình đã từ chối trả lời câu hỏi này."


class AnthropicLLM:
    def __init__(
        self, settings: LLMSettings, api_key: str, client: Anthropic | None = None
    ) -> None:
        self._settings = settings
        self._client = client or Anthropic(
            api_key=api_key,
            timeout=settings.timeout,
            # None keeps the SDK default (api.anthropic.com); set it to reach a
            # gateway that speaks the Messages API.
            base_url=settings.base_url or None,
        )

    def generate(self, messages: list[dict[str, str]]) -> GenerationResult:
        system, turns = self._split_system(messages)

        request: dict[str, Any] = {
            "model": self._settings.model,
            "max_tokens": self._settings.max_tokens,
            "messages": turns,
        }
        if system:
            request["system"] = system
        if self._settings.effort:
            request["output_config"] = {"effort": self._settings.effort}
        # No temperature: current Claude models reject it outright.

        response = self._client.messages.create(**request)

        # A declined request is a successful HTTP 200 with an empty content list, so
        # the stop reason has to be read before the content, not after.
        if response.stop_reason == "refusal":
            logger.warning("anthropic declined the request (model=%s)", response.model)
            text = REFUSAL_ANSWER
        else:
            text = "".join(block.text for block in response.content if block.type == "text")

        usage = response.usage
        return GenerationResult(
            text=text,
            model=response.model,
            prompt_tokens=usage.input_tokens if usage else 0,
            completion_tokens=usage.output_tokens if usage else 0,
        )

    @staticmethod
    def _split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        """Lift system turns out of the list.

        The Messages API takes the system prompt as its own top-level parameter. Left in
        the list it would either be rejected or read as an ordinary turn, which would
        silently drop the grounding rules that keep answers tied to the retrieved
        passages.
        """
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        return system, turns

    def health(self) -> bool:
        # Lists rather than retrieves: gateways that implement the Messages API often
        # serve GET /v1/models but not GET /v1/models/{id}, and a 404 there would report
        # the whole LLM as down while generation works fine.
        try:
            self._client.models.list()
        except Exception as exc:
            logger.warning("llm health check failed: %s", exc)
            return False
        return True
