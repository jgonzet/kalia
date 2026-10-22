"""LLM client for the Claude API (Anthropic SDK)."""

import anthropic

from app.llm import LLMError

# The longest answer the model may write. The largest extraction of the sample dataset is about 1000 tokens (estimated as
# characters / 3), but models that think before answering spend part of this limit on the thinking, so it is set well above.
MAX_OUTPUT_TOKENS = 8192


class AnthropicLLM:
    """Client of the Claude API. It takes no base URL on purpose: it always talks to Anthropic's default address.

    The Docker image sets `LLM_BASE_URL` to the host's Ollama, so inside the container that variable always has a value,
    and the app cannot tell whether the user set it. Using it here would send the Claude key to the Ollama address.
    """

    def __init__(self, model: str, api_key: str, timeout_seconds: float) -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds)

    def complete(self, prompt: str) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_OUTPUT_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        if response.stop_reason == "max_tokens":
            raise LLMError(f"LLM answer was cut off at {MAX_OUTPUT_TOKENS} tokens")
        if response.stop_reason == "refusal":
            raise LLMError("LLM declined to answer")
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text:
            raise LLMError("LLM returned an empty answer")
        return text
