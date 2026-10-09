"""Builds the extraction prompt for one document."""

from pathlib import Path
from string import Template

from app.models import Catalog, Document

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "extract_commitments.md"


def build_prompt(document: Document, catalog: Catalog) -> str:
    """Return the full prompt: instructions, the response contract, the catalog and the document."""
    people = "\n".join(f"- {p.name} ({p.role})" for p in catalog.people)
    projects = "\n".join(f"- {p.name}: {p.description}" for p in catalog.projects)
    return Template(_PROMPT_PATH.read_text(encoding="utf-8")).substitute(
        people=people,
        projects=projects,
        document_id=document.id,
        document_type=document.type,
        document_date=document.date.isoformat(),
        participants=", ".join(document.participants),
        text=document.text,
    )
