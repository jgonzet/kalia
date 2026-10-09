"""Shared data shapes passed between modules."""

from dataclasses import dataclass
from datetime import date
from typing import Literal

DocumentType = Literal["email", "meeting", "chat"]


@dataclass(frozen=True)
class Document:
    """A normalized input: every source (email, transcript, chat) becomes one of these."""

    id: str
    type: DocumentType
    date: date
    participants: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    role: str
    area: str
    level: int
    reports_to: str | None  # id of the manager


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    description: str
    status: str
    deadline: date | None


@dataclass(frozen=True)
class Catalog:
    """The fictional company: the user, its people and its active projects."""

    user: str
    people: tuple[Person, ...]
    projects: tuple[Project, ...]


@dataclass(frozen=True)
class Commitment:
    """Someone committed to someone else to do something, optionally by a date.

    `who_id`, `to_whom_id` and `project_id` are catalog ids. All commitments are open: V0 has no status.
    """

    id: str
    owner_id: str
    who_id: str
    to_whom_id: str
    what: str
    due: date | None
    project_id: str | None
    document_id: str
    document_date: date
