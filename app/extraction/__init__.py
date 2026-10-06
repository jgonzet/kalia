"""Extraction: finds commitments in a document using the LLM."""

from typing import Protocol

from app.models import Catalog, Commitment, Document


class CommitmentExtractor(Protocol):
    def extract(self, document: Document, catalog: Catalog) -> list[Commitment]:
        """Return the commitments found in the document, linked to catalog people and projects."""
        ...
