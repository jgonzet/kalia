"""Reads the commitments already written in a dataset's `expected` files; nothing is extracted."""

import json
from datetime import date
from pathlib import Path

from app.models import Catalog, Commitment, Document


class ExpectedCommitmentsReader:
    """Copies the precomputed commitments of `<company_dir>/expected/<document id>.json` (format in docs/DATASET.md).

    It implements `CommitmentExtractor` only so that `load_dataset` can take it in place of an LLM extractor.
    """

    def __init__(self, company_dir: Path, owner_id: str) -> None:
        self._dir = company_dir / "expected"
        self._owner_id = owner_id

    def extract(self, document: Document, catalog: Catalog) -> list[Commitment]:
        """Return the document's commitments with names turned into catalog ids; no file or no annotations means none."""
        path = self._dir / f"{document.id}.json"
        if not path.is_file():
            return []
        people = {p.name: p.id for p in catalog.people}
        projects = {p.name: p.id for p in catalog.projects}
        items = json.loads(path.read_text(encoding="utf-8")).get("extractions", {}).get("commitments", [])
        return [
            Commitment(
                id=c["id"],
                owner_id=self._owner_id,
                who_id=people[c["who"]],
                to_whom_id=people[c["to_whom"]],
                what=c["what"],
                due=date.fromisoformat(c["due"]) if c["due"] else None,
                project_id=projects[c["project"]] if c["project"] else None,
                document_id=document.id,
                document_date=document.date,
            )
            for c in items
        ]
