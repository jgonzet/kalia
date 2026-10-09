"""SQLite implementation of the document and catalog stores."""

import json
import sqlite3
from datetime import date

from app.models import Catalog, Document, DocumentType, Person, Project

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
CREATE TABLE IF NOT EXISTS catalog_meta (
    owner_id TEXT PRIMARY KEY,
    user_name TEXT NOT NULL
);
"""


class SqliteStore:
    """Stores documents and the catalog in a SQLite file; every row carries the owner id."""

    def __init__(self, db_path: str, owner_id: str) -> None:
        self._db_path = db_path
        self._owner_id = owner_id
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

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
