"""Answering: retrieves relevant commitments and answers a question with the LLM."""

from typing import Protocol


class Answerer(Protocol):
    def answer(self, question: str) -> str:
        """Answer the question using only the stored commitments relevant to it."""
        ...
