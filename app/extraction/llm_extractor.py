"""Extractor that asks an LLM client directly: build the prompt, call, parse."""

import logging

from app.extraction.parse import parse_response
from app.extraction.prompt import build_prompt
from app.llm import LLMClient
from app.models import Catalog, Commitment, Document

logger = logging.getLogger(__name__)


class LLMExtractor:
    """Implements `CommitmentExtractor` over any `LLMClient`; raises LLMError if the call fails."""

    def __init__(self, llm: LLMClient, owner_id: str) -> None:
        self._llm = llm
        self._owner_id = owner_id

    def extract(self, document: Document, catalog: Catalog) -> list[Commitment]:
        """Return the valid commitments of the answer; invalid items are logged and left out."""
        answer = self._llm.complete(build_prompt(document, catalog))
        result = parse_response(answer, document, catalog, self._owner_id)
        for problem in result.problems:
            logger.warning(problem)
        return result.commitments
