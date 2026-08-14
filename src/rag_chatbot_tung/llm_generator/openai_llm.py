"""OpenAI-backed implementation of LLMProvider."""

from __future__ import annotations

from openai import OpenAI

from rag_chatbot_tung.configs import LLMSettings
from rag_chatbot_tung.logging import get_logger
from rag_chatbot_tung.validate import GenerationResult

logger = get_logger(__name__)


class OpenAILLM:
    def __init__(self, settings: LLMSettings, api_key: str) -> None:
        self._settings = settings
        self._client = OpenAI(
            api_key=api_key, timeout=settings.timeout, base_url=settings.base_url or None
        )

    def generate(self, messages: list[dict[str, str]]) -> GenerationResult:
        response = self._client.chat.completions.create(
            model=self._settings.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
        )
        usage = response.usage
        return GenerationResult(
            text=response.choices[0].message.content or "",
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )

    def health(self) -> bool:
        try:
            self._client.models.retrieve(self._settings.model)
        except Exception as exc:
            logger.warning("llm health check failed: %s", exc)
            return False
        return True
