"""Storage: persists commitments, documents and the catalog behind interfaces, so the backing database can change."""

from typing import Protocol

from app.models import Catalog, Commitment, Document


class CommitmentStore(Protocol):
    def save_document_commitments(self, document_id: str, commitments: list[Commitment]) -> None:
        """Store the commitments of a document; re-saving the same document must not duplicate them."""
        ...

    def list_commitments(self) -> list[Commitment]:
        """Return every stored commitment."""
        ...


class DocumentStore(Protocol):
    def save_document(self, document: Document) -> None:
        """Store a document; saving an id that already exists replaces it instead of duplicating it."""
        ...

    def get_document(self, document_id: str) -> Document | None:
        """Return the document with this id, or None."""
        ...

    def list_documents(self) -> list[Document]:
        """Return every stored document, ordered by id."""
        ...


class CatalogStore(Protocol):
    def save_catalog(self, catalog: Catalog) -> None:
        """Store the catalog; saving it again replaces the previous one."""
        ...

    def load_catalog(self) -> Catalog | None:
        """Return the stored catalog, or None if none was saved."""
        ...


class Store(DocumentStore, CatalogStore, Protocol):
    """Everything the ingestion side needs from storage."""
