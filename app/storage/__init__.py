"""Storage: persists commitments behind an interface, so the backing database can change."""

from typing import Protocol

from app.models import Commitment


class CommitmentStore(Protocol):
    def save_document_commitments(self, document_id: str, commitments: list[Commitment]) -> None:
        """Store the commitments of a document; re-saving the same document must not duplicate them."""
        ...

    def list_commitments(self) -> list[Commitment]:
        """Return every stored commitment."""
        ...
