"""Tests of the run log (scripts/run_log.py)."""

from pathlib import Path

import pytest

import run_log


def test_a_run_is_appended_and_read_back(tmp_path: Path) -> None:
    log = tmp_path / "nested" / "metrics.jsonl"  # the folder does not exist yet
    first = run_log.append_run("retrieval", {"retriever": "A"}, {"recall": 1.0}, {"q1": {"missing": 0}}, path=log)
    second = run_log.append_run("extraction", {"model": "m"}, {"recall": 0.5}, {}, path=log)
    assert run_log.read_runs(log) == [first, second]
    assert first["stage"] == "retrieval" and first["git"]["commit"]


def test_no_file_means_no_runs(tmp_path: Path) -> None:
    assert run_log.read_runs(tmp_path / "absent.jsonl") == []


def test_a_corrupt_line_is_skipped_with_a_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "metrics.jsonl"
    good = run_log.append_run("retrieval", {}, {}, {}, path=log)
    log.write_text(log.read_text(encoding="utf-8") + "{not json\n\n", encoding="utf-8")
    assert run_log.read_runs(log) == [good]
    assert "metrics.jsonl:2 is not valid JSON" in capsys.readouterr().err


def test_outside_a_git_repository_the_run_is_still_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_log, "ROOT", tmp_path)  # a folder that is not a repository
    assert run_log.git_state() == {"commit": "unknown", "dirty": True}
    record = run_log.append_run("retrieval", {}, {}, {}, path=tmp_path / "metrics.jsonl")
    assert record["git"]["commit"] == "unknown"


def test_without_git_installed_the_run_is_still_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # no git here
    assert run_log.git_state()["commit"] == "unknown"
