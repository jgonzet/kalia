"""Tests of the measurement of the retrieval (scripts/evaluate_retrieval.py), with made-up results and a fake retriever."""

from datetime import date
from pathlib import Path

import evaluate_retrieval as ev
from app.models import Commitment


def result(name: str, expected: int, retrieved: int, matched: int, known_gap: str | None = None) -> ev.QuestionResult:
    return ev.QuestionResult(name, "category", expected, retrieved, matched, known_gap)


class FixedRetriever:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def retrieve(self, question: str) -> list[Commitment]:
        return [Commitment(i, "o", "a", "b", "x", None, None, "d", date(2026, 1, 1)) for i in self._ids]


def test_missing_and_extra_are_counted_against_the_expected_ids() -> None:
    r = ev.measure("q", "c", FixedRetriever(["a", "b", "z"]), "question", ["a", "c"])
    assert (r.expected, r.retrieved, r.matched, r.missing, r.extra) == (2, 3, 1, 1, 2)


def test_totals_add_counts_and_do_not_average_percentages() -> None:
    total = ev.add_up([result("big", 100, 100, 100), result("small", 2, 4, 1)])
    assert (total.expected, total.retrieved, total.matched) == (102, 104, 101)
    assert round(total.recall, 4) == round(101 / 102, 4) and round(total.precision, 4) == round(101 / 104, 4)
    assert (total.exact, total.full_coverage) == (1, 1)


def test_an_empty_expected_answer_gives_full_recall() -> None:
    assert ev.add_up([result("none", 0, 5, 0)]).recall == 1.0


def test_a_known_gap_is_not_an_unexpected_loss() -> None:
    lost = ev.unexpected_missing([result("gap", 3, 1, 1, known_gap="needs the LLM"), result("bug", 3, 1, 1), result("fine", 3, 3, 3)])
    assert [r.name for r in lost] == ["bug"]


def test_latest_version_of_each_question_is_the_one_measured(tmp_path: Path) -> None:
    path = tmp_path / "questions.jsonl"
    path.write_text('{"id": "q1", "version": "v1", "x": 1}\n{"id": "q2", "version": "v1"}\n{"id": "q1", "version": "v2", "x": 2}\n', encoding="utf-8")
    assert {q["id"]: q["version"] for q in ev.load_latest_questions(path)} == {"q1": "v2", "q2": "v1"}


def test_a_question_without_after_held_out_or_category_is_still_measured() -> None:
    questions = [{"id": "q", "version": "v1", "question": "?", "expected": ["a"]}]  # fields a hand-written file might lack
    results = ev.measure_suite(questions, {"initial": FixedRetriever(["a"]), "after": FixedRetriever([])})  # type: ignore[arg-type]
    assert [(r.name, r.category, r.missing) for r in results] == [("q", "uncategorised", 0)]


def test_a_question_with_a_held_out_document_is_measured_twice() -> None:
    questions = [{"id": "q", "version": "v1", "category": "c", "question": "?", "expected": ["a"], "after_held_out": {"document": "d", "expected": ["a", "b"]}}]
    results = ev.measure_suite(questions, {"initial": FixedRetriever(["a"]), "after": FixedRetriever(["a"])})  # type: ignore[arg-type]
    assert [(r.name, r.missing) for r in results] == [("q", 0), ("q@after", 1)]


def test_the_known_gap_travels_from_the_question_to_its_results() -> None:
    questions = [{"id": "q", "version": "v1", "category": "c", "question": "?", "expected": ["a"], "after_held_out": None, "known_gap": "needs the LLM; issue #22"}]
    results = ev.measure_suite(questions, {"initial": FixedRetriever([]), "after": FixedRetriever([])})  # type: ignore[arg-type]
    assert results[0].known_gap == "needs the LLM; issue #22" and ev.unexpected_missing(results) == []
