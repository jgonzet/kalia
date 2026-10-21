"""LLM client for Ollama's native API, which lets each request set the context window (`/v1` ignores it)."""

import json
import urllib.error
import urllib.request

from app.llm import LLMError

TIMEOUT_SECONDS = 60.0


class OllamaLLM:
    def __init__(self, base_url: str, model: str, context_tokens: int) -> None:
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._context_tokens = context_tokens

    def complete(self, prompt: str) -> str:
        body = {
            "model": self._model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"num_ctx": self._context_tokens},
        }
        request = urllib.request.Request(self._url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                content = json.load(response)["message"]["content"]
        except (OSError, ValueError, KeyError, TypeError) as exc:  # urllib errors are OSError; bad JSON is ValueError
            raise LLMError(f"LLM request failed: {exc}") from exc
        if not content:
            raise LLMError("LLM returned an empty answer")
        return content
