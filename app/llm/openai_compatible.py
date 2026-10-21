"""LLM client for any OpenAI-compatible endpoint (Ollama by default)."""

import openai

from app.llm import LLMError

TIMEOUT_SECONDS = 60.0


class OpenAICompatibleLLM:
    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self._model = model
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=TIMEOUT_SECONDS)

    def complete(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
        except openai.OpenAIError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise LLMError("LLM returned an empty answer")
        return content
