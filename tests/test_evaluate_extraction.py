"""Tests of how the extraction evaluation logs a run (scripts/quality/evals/evaluate_extraction.py), with made-up results."""

from pathlib import Path

import scripts.quality.evals.evaluate_extraction as ev
from scripts.quality import run_log


def document(document_id: str, expected: int, extracted: int, matched: int, field_errors: int = 0) -> ev.DocumentResult:
    matches = [ev.Match(f"e{i}", f"x{i}", due_ok=i >= field_errors, project_ok=True) for i in range(matched)]
    missing = [object()] * (expected - matched)  # only their number matters
    extra = [object()] * (extracted - matched)
    return ev.DocumentResult(document_id, expected, extracted, matches=matches, missing=missing, extra=extra)  # type: ignore[arg-type]


def test_a_run_is_logged_with_totals_and_per_document_counts(tmp_path: Path) -> None:
    log = tmp_path / "metrics.jsonl"
    results = [document("d1", expected=10, extracted=9, matched=8, field_errors=1), document("d2", expected=2, extracted=3, matched=2)]
    record = ev.log_run(results, "acme", "some-model", "runs/other.db", path=log)
    assert record["stage"] == "extraction"
    assert record["params"]["model"] == "some-model" and record["params"]["database"] == "other.db" and record["params"]["dataset"] == "acme"
    metrics = record["metrics"]
    assert (metrics["expected"], metrics["extracted"], metrics["matched"], metrics["missing"], metrics["extra"]) == (12, 12, 10, 2, 2)
    assert metrics["due_ok"] == 9
    assert record["details"]["d1"] == {"expected": 10, "extracted": 9, "matched": 8, "missing": 2, "extra": 1, "field_errors": 1}
    assert run_log.read_runs(log) == [record]
