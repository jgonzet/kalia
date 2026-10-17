"""Answers a question with the LLM, using only the commitments the retriever returns."""

from datetime import date
from pathlib import Path

from app.answering import Answer, Retriever
from app.answering.prompt import PROMPT_PATH, build_prompt, person_names
from app.llm import LLMClient, LLMError
from app.storage import Store

DEGRADED_TEXT = "No pude generar la respuesta ahora. Estos son los compromisos relacionados con tu pregunta."


class LLMAnswerer:
    """Retrieves the commitments for a question and asks the LLM to answer from them."""

    def __init__(self, llm: LLMClient, retriever: Retriever, store: Store, today: date, prompt: Path = PROMPT_PATH) -> None:
        self._llm = llm
        self._retriever = retriever
        self._store = store
        self._today = today
        self._prompt = prompt

    def answer(self, question: str) -> Answer:
        """Return the LLM's answer; if the call fails or comes back empty, return the commitments with `degraded` set."""
        catalog = self._store.load_catalog()
        commitments = self._retriever.retrieve(question, catalog)
        people = person_names(catalog)
        prompt = build_prompt(question, commitments, catalog, self._today, self._prompt)
        try:
            text = self._llm.complete(prompt).strip()
        except LLMError:
            text = ""
        if not text:
            return Answer(DEGRADED_TEXT, commitments, degraded=True, people=people)
        return Answer(text, commitments, degraded=False, people=people)
