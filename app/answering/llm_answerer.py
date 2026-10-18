"""Answers a question with the LLM, using only the commitments the retriever returns."""

from datetime import date
from pathlib import Path

from app.answering import Answer, Retriever
from app.answering.prompt import PROMPT_PATH, build_prompt, person_names
from app.llm import LLMClient, LLMError
from app.llm.tokens import fits_context
from app.storage import Store

DEGRADED_TEXT = "No pude generar la respuesta ahora. Estos son los compromisos relacionados con tu pregunta."
TOO_LONG_TEXT = (
    "Tu pregunta trae demasiados compromisos para leerlos todos juntos y no quiero responder con una parte. "
    "Estos son los relacionados con tu pregunta; probá preguntar por una persona o por una semana."
)


class LLMAnswerer:
    """Retrieves the commitments for a question and asks the LLM to answer from them."""

    def __init__(
        self,
        llm: LLMClient,
        retriever: Retriever,
        store: Store,
        today: date,
        prompt: Path = PROMPT_PATH,
        context_tokens: int | None = None,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._store = store
        self._today = today
        self._prompt = prompt
        self._context_tokens = context_tokens

    def answer(self, question: str) -> Answer:
        """Return the LLM's answer; if the call fails, comes back empty, or the prompt does not fit the context window
        (`context_tokens`, if known), return the commitments with `degraded` set and the LLM is not called."""
        catalog = self._store.load_catalog()
        commitments = self._retriever.retrieve(question, catalog)
        people = person_names(catalog)
        prompt = build_prompt(question, commitments, catalog, self._today, self._prompt)
        if not fits_context(prompt, self._context_tokens):
            return Answer(TOO_LONG_TEXT, commitments, degraded=True, people=people)
        try:
            text = self._llm.complete(prompt).strip()
        except LLMError:
            text = ""
        if not text:
            return Answer(DEGRADED_TEXT, commitments, degraded=True, people=people)
        return Answer(text, commitments, degraded=False, people=people)
