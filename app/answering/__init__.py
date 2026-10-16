"""Answering: retrieves relevant commitments and answers a question with the LLM."""

from typing import Protocol

from app.models import Commitment


class Retriever(Protocol):
    def retrieve(self, question: str) -> list[Commitment]:
        """Return the stored commitments relevant to the question, ordered by id."""
        ...


class Answerer(Protocol):
    def answer(self, question: str) -> str:
        """Answer the question using only the stored commitments relevant to it."""
        ...
