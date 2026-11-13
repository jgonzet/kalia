"""Reads a saved extraction: what a real LLM or flow extracted once, kept in `data/<company>/extracted/` (format in docs/DATASET.md)."""

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TypedDict

from app.extraction.parse import ExtractedCommitment, parse_items
from app.models import Catalog, Commitment, Document

logger = logging.getLogger(__name__)

EXTRACTED_DIR = "extracted"


class SavedExtractionFile(TypedDict):
    """The content of a saved extraction file."""

    id: str
    company: str
    model: str
    date: str
    documents: dict[str, list[ExtractedCommitment]]


@dataclass(frozen=True)
class SavedExtractionInfo:
    """What the chat page tells the person about a saved extraction: which one it is and who made it, and when."""

    id: str
    model: str
    date: date


def find_saved_extraction(company_dir: Path) -> Path:
    """Return the saved extraction file of a company: the newest one. This is the one place that decides which file the app loads.

    The file name starts with the date (`<YYYYMMDD>-<model>`), so the last one by name is the newest; older ones stay as history.
    Raises ValueError if the company has none.
    """
    files = sorted((company_dir / EXTRACTED_DIR).glob("*.json"))
    if not files:
        raise ValueError(
            f"no saved extraction in {company_dir / EXTRACTED_DIR}: add one, or set COMMITMENTS_SOURCE=extraction to extract with your LLM"
        )
    return files[-1]


class SavedExtractionReader:
    """Gives the commitments of a saved extraction file, document by document, validated like the answer of a live LLM.

    It implements `CommitmentExtractor` only so that `load_dataset` can take it in place of an LLM extractor. Names are
    turned into catalog ids and ids are given to the commitments here, as with a live extraction; an item that does not
    validate is logged and left out. A document that is not in the file gets no commitments.
    """

    def __init__(self, path: Path, company_id: str, owner_id: str) -> None:
        """Read and check the file's header; raise ValueError naming the file if it is unusable or belongs to another company."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}: not valid JSON ({exc})") from None
        missing = {"id", "company", "model", "date", "documents"} - set(data if isinstance(data, dict) else ())
        if missing:
            raise ValueError(f"{path.name}: missing {sorted(missing)}")
        if data["id"] != path.stem:
            raise ValueError(f"{path.name}: the id inside is {data['id']!r}, it must be the file name")
        if data["company"] != company_id:
            raise ValueError(f"{path.name}: it is an extraction of {data['company']!r}, not of {company_id!r}")
        try:
            extraction_date = date.fromisoformat(data["date"])
        except ValueError:
            raise ValueError(f"{path.name}: date must be YYYY-MM-DD, got {data['date']!r}") from None
        self._documents: dict[str, list[ExtractedCommitment]] = data["documents"]
        self._owner_id = owner_id
        self.info = SavedExtractionInfo(data["id"], data["model"], extraction_date)

    def extract(self, document: Document, catalog: Catalog) -> list[Commitment]:
        """Return the document's saved commitments as `Commitment`s; none if the document is not in the file."""
        result = parse_items(self._documents.get(document.id, []), document, catalog, self._owner_id)
        for problem in result.problems:
            logger.warning("saved extraction %s: %s", self.info.id, problem)
        return result.commitments
