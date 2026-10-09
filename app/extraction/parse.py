"""Reads and validates the model's answer for one document (the response contract)."""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import TypedDict

from app.models import Catalog, Commitment, Document

_KEYS = {"who", "to_whom", "what", "due", "project"}


class ExtractedCommitment(TypedDict):
    """One item of the response contract, before it is linked to a document."""

    who: str
    to_whom: str
    what: str
    due: str | None
    project: str | None


@dataclass(frozen=True)
class ParseResult:
    commitments: list[Commitment]
    problems: list[str]


def parse_response(text: str, document: Document, catalog: Catalog, owner_id: str) -> ParseResult:
    """Parse a raw model answer (a JSON list, possibly inside a code fence) for one document."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        items = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return ParseResult([], [f"{document.id}: the answer is not valid JSON ({exc})"])
    return parse_items(items, document, catalog, owner_id)


def parse_items(items: object, document: Document, catalog: Catalog, owner_id: str) -> ParseResult:
    """Validate a decoded answer; invalid items are reported and left out, valid ones become Commitments."""
    if not isinstance(items, list):
        return ParseResult([], [f"{document.id}: expected a JSON list, got {type(items).__name__}"])
    people = {p.name for p in catalog.people}
    projects = {p.name for p in catalog.projects}
    commitments: list[Commitment] = []
    problems: list[str] = []
    for index, item in enumerate(items, start=1):
        label = f"{document.id} item {index}"
        if not isinstance(item, dict):
            problems.append(f"{label}: not an object")
            continue
        extra = set(item) - _KEYS
        if extra:
            problems.append(f"{label}: unexpected keys {sorted(extra)} ignored")
        missing = _KEYS - set(item)
        if missing:
            problems.append(f"{label}: missing keys {sorted(missing)}, left out")
            continue
        error = _check_item(item, people, projects)
        if error:
            problems.append(f"{label}: {error}, left out")
            continue
        commitments.append(
            Commitment(
                id=f"{document.id}-c{len(commitments) + 1}",
                owner_id=owner_id,
                who=item["who"],
                to_whom=item["to_whom"],
                what=item["what"],
                due=date.fromisoformat(item["due"]) if item["due"] else None,
                project=item["project"],
                document_id=document.id,
                document_date=document.date,
            )
        )
    return ParseResult(commitments, problems)


def _check_item(item: dict[str, object], people: set[str], projects: set[str]) -> str | None:
    """Return why an item breaks the contract, or None if it is valid."""
    for key in ("who", "to_whom"):
        if item[key] not in people:
            return f"{key} {item[key]!r} is not in the catalog"
    if not isinstance(item["what"], str) or not item["what"].strip():
        return "what is empty"
    if item["project"] is not None and item["project"] not in projects:
        return f"project {item['project']!r} is not in the catalog"
    if item["due"] is not None:
        try:
            date.fromisoformat(str(item["due"]))
        except ValueError:
            return f"due {item['due']!r} is not a YYYY-MM-DD date"
    return None
