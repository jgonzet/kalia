"""Tests of the measurement of the retrieval (scripts/evaluate_retrieval.py), with made-up results and a fake retriever."""

from datetime import date

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


def test_latest_version_of_each_question_is_the_one_measured(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "questions.jsonl"
    path.write_text('{"id": "q1", "version": "v1", "x": 1}\n{"id": "q2", "version": "v1"}\n{"id": "q1", "version": "v2", "x": 2}\n', encoding="utf-8")
    assert {q["id"]: q["version"] for q in ev.load_latest_questions(path)} == {"q1": "v2", "q2": "v1"}
