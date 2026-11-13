import json
import logging
from datetime import date
from pathlib import Path

import pytest

from app.config import ROOT
from app.extraction.saved import EXTRACTED_DIR, SavedExtractionReader, find_saved_extraction
from app.ingestion.dataset import DatasetSource
from app.models import Document

COMPANY = ROOT / "data" / "lamanija"
OWNER = "local"
FILE_ID = "20261009-testflow"


def write_saved(tmp_path: Path, documents: dict[str, list[dict[str, str | None]]], **header: str) -> Path:
    """Write a small saved extraction file and return its path."""
    content = {"id": FILE_ID, "company": "lamanija", "model": "Test flow", "date": "2026-10-09", "documents": documents} | header
    path = tmp_path / f"{content['id']}.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


ITEM = {"who": "Milhouse Van Houten", "to_whom": "Lalo Landa", "what": "Pasar la lista de bugs abiertos", "due": "2026-09-16", "project": "Motocrotos Adventures"}


def test_reader_turns_names_into_catalog_ids(tmp_path: Path) -> None:
    source = DatasetSource(COMPANY)
    catalog = source.catalog()
    document = source.document("lamanija-0001")
    reader = SavedExtractionReader(write_saved(tmp_path, {"lamanija-0001": [ITEM, ITEM | {"due": None}]}), "lamanija", OWNER)
    commitments = reader.extract(document, catalog)
    people = {p.name: p.id for p in catalog.people}
    projects = {p.name: p.id for p in catalog.projects}
    first = commitments[0]
    assert [c.id for c in commitments] == ["lamanija-0001-c1", "lamanija-0001-c2"]
    assert first.who_id == people["Milhouse Van Houten"] and first.to_whom_id == people["Lalo Landa"]
    assert first.due == date(2026, 9, 16) and first.project_id == projects["Motocrotos Adventures"]
    assert first.document_id == document.id and first.document_date == document.date and first.owner_id == OWNER
    assert (reader.info.id, reader.info.model, reader.info.date) == (FILE_ID, "Test flow", date(2026, 10, 9))


def test_an_item_with_an_unknown_name_is_left_out_and_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    source = DatasetSource(COMPANY)
    reader = SavedExtractionReader(write_saved(tmp_path, {"lamanija-0001": [ITEM | {"who": "Nobody Known"}, ITEM]}), "lamanija", OWNER)
    with caplog.at_level(logging.WARNING):
        commitments = reader.extract(source.document("lamanija-0001"), source.catalog())
    assert [c.id for c in commitments] == ["lamanija-0001-c1"]
    assert FILE_ID in caplog.text and "Nobody Known" in caplog.text


def test_a_document_that_is_not_in_the_file_gets_no_commitments(tmp_path: Path) -> None:
    reader = SavedExtractionReader(write_saved(tmp_path, {}), "lamanija", OWNER)
    document = Document("not-in-the-file", "email", date(2026, 1, 1), ("A",), "hi")
    assert reader.extract(document, DatasetSource(COMPANY).catalog()) == []


def test_the_shipped_extraction_has_no_problems() -> None:
    """Every item of the file the app ships with passes the same validation as a live answer."""
    source = DatasetSource(COMPANY)
    catalog = source.catalog()
    reader = SavedExtractionReader(find_saved_extraction(COMPANY), "lamanija", OWNER)
    saved = json.loads(find_saved_extraction(COMPANY).read_text(encoding="utf-8"))["documents"]
    for document in source.documents():
        assert len(reader.extract(document, catalog)) == len(saved[document.id]), document.id


def test_a_company_without_a_saved_extraction_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no saved extraction"):
        find_saved_extraction(tmp_path)


def test_with_several_saved_extractions_the_newest_is_used(tmp_path: Path) -> None:
    folder = tmp_path / EXTRACTED_DIR
    folder.mkdir()
    for name in ("20261010-b", "20261009-a", "20261009-a-2"):
        (folder / f"{name}.json").write_text("{}", encoding="utf-8")
    assert find_saved_extraction(tmp_path).name == "20261010-b.json"


def test_find_returns_the_only_file(tmp_path: Path) -> None:
    folder = tmp_path / EXTRACTED_DIR
    folder.mkdir()
    (folder / "20261009-a.json").write_text("{}", encoding="utf-8")
    assert find_saved_extraction(tmp_path) == folder / "20261009-a.json"


@pytest.mark.parametrize(
    ("header", "message"),
    [
        ({"id": "20261009-other"}, "must be the file name"),
        ({"company": "elsewhere"}, "not of 'lamanija'"),
        ({"date": "09/10/2026"}, "YYYY-MM-DD"),
    ],
)
def test_a_file_that_does_not_fit_is_refused_naming_the_file(tmp_path: Path, header: dict[str, str], message: str) -> None:
    path = write_saved(tmp_path, {}, **header)
    if "id" in header:
        path = path.rename(tmp_path / f"{FILE_ID}.json")  # the id inside no longer matches the name
    with pytest.raises(ValueError, match=message) as error:
        SavedExtractionReader(path, "lamanija", OWNER)
    assert path.name in str(error.value)


def test_a_file_that_is_not_json_or_lacks_fields_is_refused(tmp_path: Path) -> None:
    broken = tmp_path / "20261009-broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        SavedExtractionReader(broken, "lamanija", OWNER)
    incomplete = tmp_path / "20261009-incomplete.json"
    incomplete.write_text(json.dumps({"id": "20261009-incomplete"}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        SavedExtractionReader(incomplete, "lamanija", OWNER)
