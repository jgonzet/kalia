"""Runs the extractor on a stored document and stores its commitments."""

import logging

from app.extraction import CommitmentExtractor
from app.llm import LLMError
from app.models import Document
from app.storage import Store

logger = logging.getLogger(__name__)


def extract_and_store(
    document: Document, extractor: CommitmentExtractor, store: Store
) -> bool:
    """Extract the document's commitments and store them; return False if that was not possible.

    A failed LLM call or a missing catalog is logged and returns False, leaving the stored commitments untouched.
    """
    catalog = store.load_catalog()
    if catalog is None:
        logger.warning("%s: no catalog stored, commitments not extracted", document.id)
        return False
    try:
        commitments = extractor.extract(document, catalog)
    except LLMError as exc:
        logger.warning("%s: extraction failed (%s)", document.id, exc)
        return False
    store.save_document_commitments(document.id, commitments)
    return True
