"""Groups retrieved commitments by project and orders them, so the LLM only has to filter and write."""

from dataclasses import dataclass
from datetime import date

from app.models import Catalog, Commitment, Project

_LAST = date.max


@dataclass(frozen=True)
class ProjectGroup:
    """The commitments of one project; `project` is None for those with no project."""

    project: Project | None
    commitments: list[Commitment]


def group_by_project(commitments: list[Commitment], catalog: Catalog | None) -> list[ProjectGroup]:
    """Group commitments by project and order them.

    Projects go by their catalog deadline (nearest first, none last), then by id; commitments without a project
    go in the last group. Inside a group the nearest due date comes first and those without one go last.
    Without a catalog, every commitment goes in one group with no project.
    """
    projects = {p.id: p for p in catalog.projects} if catalog else {}
    by_project: dict[str | None, list[Commitment]] = {}
    for commitment in commitments:
        key = commitment.project_id if commitment.project_id in projects else None
        by_project.setdefault(key, []).append(commitment)

    keys = sorted((k for k in by_project if k is not None), key=lambda project_id: _project_order(projects[project_id]))
    if None in by_project:
        keys.append(None)
    return [
        ProjectGroup(projects[k] if k is not None else None, sorted(by_project[k], key=_commitment_order))
        for k in keys
    ]


def due_state(commitment: Commitment, today: date) -> str:
    """Whether the due date has passed: "sin fecha", "atrasado" (before today) or "pendiente" (today or later).

    The words are Spanish because the model reads them in the prompt. V0 has no commitment status, so "atrasado"
    only says the date passed, not that nothing was done.
    """
    if commitment.due is None:
        return "sin fecha"
    return "atrasado" if commitment.due < today else "pendiente"


def _project_order(project: Project) -> tuple[date, str]:
    return project.deadline or _LAST, project.id


def _commitment_order(commitment: Commitment) -> tuple[date, str]:
    return commitment.due or _LAST, commitment.id
