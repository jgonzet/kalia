"""Answering: retrieves relevant commitments and answers a question with the LLM."""

from dataclasses import dataclass, field
from typing import Protocol

from app.models import Commitment


@dataclass(frozen=True)
class Answer:
    """What the chat returns: the text, the commitments it was built from, and whether the LLM failed.

    `people` maps the catalog id of each person to the name, so the commitments can be shown with names.
    """

    text: str
    commitments: list[Commitment]
    degraded: bool
    people: dict[str, str] = field(default_factory=dict)


class Retriever(Protocol):
    def retrieve(self, question: str) -> list[Commitment]:
        """Return the stored commitments relevant to the question, ordered by id."""
        ...


class Answerer(Protocol):
    def answer(self, question: str) -> Answer:
        """Answer the question using only the stored commitments relevant to it; never raises on LLM failure."""
        ...
