import sqlite3
from datetime import date
from pathlib import Path

import pytest

from app.models import Catalog, Commitment, Document, Person, Project
from app.storage.sqlite import SqliteStore


def commitment(number: int, document: str = "d") -> Commitment:
    return Commitment(f"{document}-c{number}", "o", "p1", "p2", f"task {number}", date(2026, 1, number), "j1", document, date(2026, 1, 1))


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(str(tmp_path / "s.db"), "o")


def test_commitments_round_trip_and_are_replaced_per_document(store: SqliteStore) -> None:
    store.save_document_commitments("d", [commitment(1), commitment(2)])
    store.save_document_commitments("e", [commitment(1, "e")])
    store.save_document_commitments("d", [commitment(3)])
    assert [c.id for c in store.list_commitments()] == ["d-c3", "e-c1"]


def test_documents_and_catalog_round_trip(store: SqliteStore) -> None:
    document = Document("d", "email", date(2026, 1, 2), ("A", "B"), "hello")
    catalog = Catalog("Ana", (Person("p1", "Ana", "dev", "it", 2, None),), (Project("j1", "Alfa", "x", "active", date(2026, 5, 1)),))
    store.save_document(document)
    store.save_catalog(catalog)
    assert store.get_document("d") == document and store.load_catalog() == catalog


def test_every_connection_is_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def recording_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)  # type: ignore[arg-type]
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    store = SqliteStore(str(tmp_path / "s.db"), "o")
    store.save_document_commitments("d", [commitment(1)])
    store.list_commitments()
    store.load_catalog()
    assert opened
    for conn in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def test_a_failed_operation_rolls_back_and_still_closes(tmp_path: Path) -> None:
    store = SqliteStore(str(tmp_path / "s.db"), "o")
    store.save_document_commitments("d", [commitment(1)])
    broken = Commitment("d-c9", "o", "p1", "p2", None, None, None, "d", date(2026, 1, 1))  # type: ignore[arg-type]
    with pytest.raises(sqlite3.IntegrityError):
        store.save_document_commitments("d", [commitment(2), broken])
    assert [c.id for c in store.list_commitments()] == ["d-c1"]
