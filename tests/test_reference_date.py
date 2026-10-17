from datetime import date
from pathlib import Path

import pytest

import app.config as config
from app.config import Settings
from app.ingestion.dataset import DatasetSource, load_dataset
from app.storage.sqlite import SqliteStore

ROOT = Path(__file__).resolve().parent.parent
DATASET_DATE = date(2026, 10, 12)


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(str(tmp_path / "t.db"), "owner")


class TestStoredReferenceDate:
    def test_none_until_saved(self, store: SqliteStore) -> None:
        assert store.load_reference_date() is None

    def test_round_trip_and_replace_and_clear(self, store: SqliteStore) -> None:
        store.save_reference_date(date(2026, 1, 2))
        assert store.load_reference_date() == date(2026, 1, 2)
        store.save_reference_date(date(2026, 3, 4))
        assert store.load_reference_date() == date(2026, 3, 4)
        store.save_reference_date(None)
        assert store.load_reference_date() is None

    def test_each_owner_has_its_own(self, tmp_path: Path) -> None:
        path = str(tmp_path / "t.db")
        SqliteStore(path, "a").save_reference_date(date(2026, 1, 2))
        assert SqliteStore(path, "b").load_reference_date() is None

    def test_a_database_created_before_this_table_still_opens(self, tmp_path: Path) -> None:
        import sqlite3

        path = str(tmp_path / "old.db")
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE commitments (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, who_id TEXT NOT NULL,"
                         " to_whom_id TEXT NOT NULL, what TEXT NOT NULL, due TEXT, project_id TEXT, document_id TEXT NOT NULL,"
                         " document_date TEXT NOT NULL)")
        assert SqliteStore(path, "owner").load_reference_date() is None

    def test_loading_the_dataset_stores_its_reference_date(self, store: SqliteStore) -> None:
        company_dir = ROOT / "data" / "lamanija"
        load_dataset(company_dir, store)
        assert store.load_reference_date() == date.fromisoformat(DatasetSource(company_dir).company["reference_date"])


class FakeDate(date):
    @classmethod
    def today(cls) -> "FakeDate":
        return cls(2030, 5, 6)


class TestResolveToday:
    def test_the_environment_wins_over_the_dataset(self) -> None:
        assert Settings(reference_date=date(2026, 3, 12)).resolve_today(DATASET_DATE) == date(2026, 3, 12)

    def test_the_dataset_wins_over_the_system_date(self) -> None:
        assert Settings().resolve_today(DATASET_DATE) == DATASET_DATE

    def test_without_either_it_is_the_system_date(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "date", FakeDate)
        assert Settings().resolve_today(None) == date(2030, 5, 6)
