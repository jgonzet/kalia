"""Ingestion: turns each input source into normalized documents and stores them."""

from collections.abc import Iterable
from typing import Protocol

from app.models import Document
from app.storage import DocumentStore


class DocumentSource(Protocol):
    def documents(self) -> Iterable[Document]:
        """Yield the normalized documents this source provides, one at a time."""
        ...


def ingest_document(document: Document, store: DocumentStore) -> None:
    """Store one normalized document; the single entry point for every source. Idempotent by id."""
    store.save_document(document)
