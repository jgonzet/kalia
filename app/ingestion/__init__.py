"""Ingestion: turns each input source into normalized documents."""

from collections.abc import Iterable
from typing import Protocol

from app.models import Document


class DocumentSource(Protocol):
    def documents(self) -> Iterable[Document]:
        """Yield the normalized documents this source provides, one at a time."""
        ...
