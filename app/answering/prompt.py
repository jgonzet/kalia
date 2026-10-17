"""Builds the answering prompt for one question and its retrieved commitments."""

from datetime import date
from pathlib import Path
from string import Template

from app.answering.ordering import ProjectGroup, due_state, group_by_project
from app.models import Catalog, Commitment

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "answer_question.md"
NO_PROJECT = "Sin proyecto"


def person_names(catalog: Catalog | None) -> dict[str, str]:
    """Map each person's catalog id to the name; empty without a catalog."""
    return {p.id: p.name for p in catalog.people} if catalog else {}


def build_prompt(
    question: str, commitments: list[Commitment], catalog: Catalog | None, today: date, template: Path = PROMPT_PATH
) -> str:
    """Return the full prompt: instructions, today's date, the commitments grouped by project, and the question.

    `template` is the file with the instructions; the default is the one the app uses, others serve to compare prompts.
    """
    people = person_names(catalog)
    groups = group_by_project(commitments, catalog)
    body = "\n\n".join(_group_text(g, people, today) for g in groups) or "(none)"
    return Template(template.read_text(encoding="utf-8")).substitute(
        user=catalog.user if catalog else "the user",
        today=today.isoformat(),
        commitments=body,
        question=question,
    )


def _group_text(group: ProjectGroup, people: dict[str, str], today: date) -> str:
    title = group.project.name if group.project else NO_PROJECT
    return "\n".join([f"## {title}"] + [_line(c, people, today) for c in group.commitments])


def _line(commitment: Commitment, people: dict[str, str], today: date) -> str:
    who = people.get(commitment.who_id, commitment.who_id)
    to_whom = people.get(commitment.to_whom_id, commitment.to_whom_id)
    due = commitment.due.isoformat() if commitment.due else "none"
    return (
        f"{commitment.id} | {who} -> {to_whom} | {commitment.what} | {due} | {due_state(commitment, today)}"
        f" | {commitment.document_id} ({commitment.document_date.isoformat()})"
    )
