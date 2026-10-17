"""SQLite implementation of the commitment, document and catalog stores."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from app.models import Catalog, Commitment, Document, DocumentType, Person, Project

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    type TEXT NOT NULL,
    date TEXT NOT NULL,
    participants TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    area TEXT NOT NULL,
    level INTEGER NOT NULL,
    reports_to TEXT
);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    deadline TEXT
);
CREATE TABLE IF NOT EXISTS commitments (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    who_id TEXT NOT NULL,
    to_whom_id TEXT NOT NULL,
    what TEXT NOT NULL,
    due TEXT,
    project_id TEXT,
    document_id TEXT NOT NULL,
    document_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS commitments_document ON commitments (owner_id, document_id);
CREATE TABLE IF NOT EXISTS catalog_meta (
    owner_id TEXT PRIMARY KEY,
    user_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dataset_meta (
    owner_id TEXT PRIMARY KEY,
    reference_date TEXT
);
"""


class SqliteStore:
    """Stores commitments, documents and the catalog in a SQLite file; every row carries the owner id."""

    def __init__(self, db_path: str, owner_id: str) -> None:
        self._db_path = db_path
        self._owner_id = owner_id
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection for one operation: it commits on success, rolls back on error and is always closed."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # sqlite3's own `with` commits or rolls back but does not close
                yield conn
        finally:
            conn.close()

    def save_document_commitments(self, document_id: str, commitments: list[Commitment]) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM commitments WHERE owner_id = ? AND document_id = ?", (self._owner_id, document_id)
            )
            conn.executemany(
                "INSERT INTO commitments (id, owner_id, who_id, to_whom_id, what, due, project_id, document_id, document_date)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        c.id,
                        self._owner_id,
                        c.who_id,
                        c.to_whom_id,
                        c.what,
                        c.due.isoformat() if c.due else None,
                        c.project_id,
                        document_id,
                        c.document_date.isoformat(),
                    )
                    for c in commitments
                ],
            )

    def list_commitments(self) -> list[Commitment]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM commitments WHERE owner_id = ? ORDER BY id", (self._owner_id,)
            ).fetchall()
        return [_commitment_from_row(row) for row in rows]

    def save_document(self, document: Document) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO documents (id, owner_id, type, date, participants, text)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    document.id,
                    self._owner_id,
                    document.type,
                    document.date.isoformat(),
                    json.dumps(document.participants),
                    document.text,
                ),
            )

    def get_document(self, document_id: str) -> Document | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id = ? AND owner_id = ?", (document_id, self._owner_id)
            ).fetchone()
        return _document_from_row(row) if row else None

    def list_documents(self) -> list[Document]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE owner_id = ? ORDER BY id", (self._owner_id,)
            ).fetchall()
        return [_document_from_row(row) for row in rows]

    def save_catalog(self, catalog: Catalog) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM people WHERE owner_id = ?", (self._owner_id,))
            conn.execute("DELETE FROM projects WHERE owner_id = ?", (self._owner_id,))
            conn.executemany(
                "INSERT INTO people (id, owner_id, name, role, area, level, reports_to)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(p.id, self._owner_id, p.name, p.role, p.area, p.level, p.reports_to) for p in catalog.people],
            )
            conn.executemany(
                "INSERT INTO projects (id, owner_id, name, description, status, deadline)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (p.id, self._owner_id, p.name, p.description, p.status, p.deadline.isoformat() if p.deadline else None)
                    for p in catalog.projects
                ],
            )
            conn.execute(
                "INSERT OR REPLACE INTO catalog_meta (owner_id, user_name) VALUES (?, ?)",
                (self._owner_id, catalog.user),
            )

    def save_reference_date(self, reference_date: date | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO dataset_meta (owner_id, reference_date) VALUES (?, ?)",
                (self._owner_id, reference_date.isoformat() if reference_date else None),
            )

    def load_reference_date(self) -> date | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT reference_date FROM dataset_meta WHERE owner_id = ?", (self._owner_id,)
            ).fetchone()
        return date.fromisoformat(row["reference_date"]) if row and row["reference_date"] else None

    def load_catalog(self) -> Catalog | None:
        with self._connect() as conn:
            meta = conn.execute(
                "SELECT user_name FROM catalog_meta WHERE owner_id = ?", (self._owner_id,)
            ).fetchone()
            if meta is None:
                return None
            people = conn.execute(
                "SELECT * FROM people WHERE owner_id = ? ORDER BY id", (self._owner_id,)
            ).fetchall()
            projects = conn.execute(
                "SELECT * FROM projects WHERE owner_id = ? ORDER BY id", (self._owner_id,)
            ).fetchall()
        return Catalog(
            user=meta["user_name"],
            people=tuple(
                Person(r["id"], r["name"], r["role"], r["area"], r["level"], r["reports_to"]) for r in people
            ),
            projects=tuple(
                Project(
                    r["id"],
                    r["name"],
                    r["description"],
                    r["status"],
                    date.fromisoformat(r["deadline"]) if r["deadline"] else None,
                )
                for r in projects
            ),
        )


def _document_from_row(row: sqlite3.Row) -> Document:
    doc_type: DocumentType = row["type"]
    return Document(
        id=row["id"],
        type=doc_type,
        date=date.fromisoformat(row["date"]),
        participants=tuple(json.loads(row["participants"])),
        text=row["text"],
    )


def _commitment_from_row(row: sqlite3.Row) -> Commitment:
    return Commitment(
        id=row["id"],
        owner_id=row["owner_id"],
        who_id=row["who_id"],
        to_whom_id=row["to_whom_id"],
        what=row["what"],
        due=date.fromisoformat(row["due"]) if row["due"] else None,
        project_id=row["project_id"],
        document_id=row["document_id"],
        document_date=date.fromisoformat(row["document_date"]),
    )
