"""LLM provider interface and the implementations selectable by configuration."""

from typing import Protocol

from app.config import DEFAULT_OLLAMA_CONTEXT_TOKENS, LLMSettings


class LLMError(Exception):
    """The LLM call failed, timed out or returned something unusable."""


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        """Send a prompt and return the model's text answer; raises LLMError on failure."""
        ...


def build_llm(llm: LLMSettings) -> LLMClient:
    """Return the LLM client selected by `llm.backend`; get `llm` from `Settings.llm_for(<task>)`."""
    if llm.backend == "fake":
        from app.llm.fake import FakeLLM

        return FakeLLM()

    if llm.backend == "ollama":
        from app.llm.ollama import OllamaLLM

        return OllamaLLM(llm.base_url, llm.model, llm.context_tokens or DEFAULT_OLLAMA_CONTEXT_TOKENS, llm.timeout_seconds)

    if llm.backend == "anthropic":
        from app.llm.anthropic import AnthropicLLM

        return AnthropicLLM(llm.model, llm.api_key, llm.timeout_seconds)

    from app.llm.openai_compatible import OpenAICompatibleLLM

    return OpenAICompatibleLLM(base_url=llm.base_url, model=llm.model, api_key=llm.api_key, timeout_seconds=llm.timeout_seconds)
