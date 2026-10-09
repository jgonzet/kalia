"""Dataset adapter: reads `data/<company>/` (format in docs/DATASET.md) as a document source."""

import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import TypedDict, cast, get_args

from app.ingestion import ingest_document
from app.models import Catalog, Document, DocumentType, Person, Project
from app.storage import Store


class CompanyInfo(TypedDict):
    id: str
    name: str
    description: str
    user_id: str
    reference_date: str
    held_out: list[str]


class DatasetSource:
    """Reads one company's dataset directory; documents in `held_out` are skipped unless asked for."""

    def __init__(self, company_dir: Path, include_held_out: bool = False) -> None:
        self._dir = company_dir
        self._include_held_out = include_held_out
        self.company: CompanyInfo = json.loads((company_dir / "company.json").read_text(encoding="utf-8"))

    def catalog(self) -> Catalog:
        """Build the catalog from `people.jsonl` and `projects.jsonl`."""
        people = tuple(
            Person(r["id"], r["name"], r["role"], r["area"], r["level"], r["reports_to"])
            for r in _read_jsonl(self._dir / "people.jsonl")
        )
        projects = tuple(
            Project(
                r["id"],
                r["name"],
                r["description"],
                r["status"],
                date.fromisoformat(r["deadline"]) if r["deadline"] else None,
            )
            for r in _read_jsonl(self._dir / "projects.jsonl")
        )
        user = next(p for p in people if p.id == self.company["user_id"])
        return Catalog(user=user.name, people=people, projects=projects)

    def documents(self) -> Iterable[Document]:
        held_out = set() if self._include_held_out else set(self.company["held_out"])
        for path in sorted((self._dir / "documents").glob("*.md")):
            if path.stem not in held_out:
                yield parse_document(path)

    def document(self, document_id: str) -> Document:
        """Read one document by id, held out or not."""
        return parse_document(self._dir / "documents" / f"{document_id}.md")


def parse_document(path: Path) -> Document:
    """Parse a document file: a `---` header of `key: value` lines, then the free text."""
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    fields = dict(line.split(": ", 1) for line in header.strip().splitlines())
    if fields["type"] not in get_args(DocumentType):
        raise ValueError(f"{path.name}: unknown document type {fields['type']!r}")
    return Document(
        id=fields["id"],
        type=cast(DocumentType, fields["type"]),
        date=date.fromisoformat(fields["date"]),
        participants=tuple(fields["participants"].split(", ")),
        text=body.strip(),
    )


def load_dataset(company_dir: Path, store: Store) -> int:
    """Store the catalog and every non-held-out document; return how many documents were ingested."""
    source = DatasetSource(company_dir)
    store.save_catalog(source.catalog())
    count = 0
    for document in source.documents():
        ingest_document(document, store)
        count += 1
    return count


def _read_jsonl(path: Path) -> list[dict[str, str | int | None]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
