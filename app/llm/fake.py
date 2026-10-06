"""Fake LLM for the smoke test and CI: ignores the prompt and returns a fixed text."""


class FakeLLM:
    def __init__(self, response: str = "fake response") -> None:
        self._response = response

    def complete(self, prompt: str) -> str:
        return self._response
