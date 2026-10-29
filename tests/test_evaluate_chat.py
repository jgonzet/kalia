import json
from dataclasses import asdict
from pathlib import Path

import pytest

from app.answering.llm_answerer import DEGRADED_TEXT
from app.llm import LLMError
from scripts.quality.evals.evaluate_chat import QuestionResult, check_degradation, evaluate, format_report, totals

ROOT = Path(__file__).resolve().parent.parent
COMPANY_DIR = ROOT / "data" / "lamanija"
SAMPLE = ["person-surname", "date-undated", "none-direction-pair"]


class EchoLLM:
    """Answers with the whole prompt, so every commitment it was given 'appears' in the answer."""

    def complete(self, prompt: str) -> str:
        return prompt


class SilentLLM:
    def complete(self, prompt: str) -> str:
        return "no sé"


class BrokenLLM:
    def complete(self, prompt: str) -> str:
        raise LLMError("down")


def run(llm: object, questions: list[str] | None = None, categories: list[str] | None = None) -> list[QuestionResult]:
    results, _, _ = evaluate(COMPANY_DIR, llm, question_filters=questions or SAMPLE, categories=categories, log=lambda _: None)  # type: ignore[arg-type]
    return results


class TestEvaluate:
    def test_an_answer_with_everything_it_was_given_says_every_needed_commitment(self) -> None:
        results = run(EchoLLM())
        assert results and all(r.said == r.needed and r.missing == 0 for r in results)

    def test_an_answer_with_nothing_leaves_out_everything_that_was_needed(self) -> None:
        results = run(SilentLLM())
        assert all(r.said == 0 and r.extra == 0 and r.missing == r.needed for r in results)

    def test_a_broken_llm_marks_every_question_degraded(self) -> None:
        results = run(BrokenLLM())
        assert all(r.degraded and r.answer == DEGRADED_TEXT for r in results)

    def test_every_question_is_measured_once_with_the_whole_dataset(self) -> None:
        assert [r.name for r in run(SilentLLM(), questions=["date-next-week"])] == ["date-next-week"]

    def test_only_the_asked_category_is_measured(self) -> None:
        results = run(SilentLLM(), questions=[""], categories=["none"])
        assert results and {r.category for r in results} == {"none"}

    def test_asking_for_nothing_that_exists_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="no question"):
            run(SilentLLM(), questions=["there-is-no-such-question"])


class TestDegradation:
    def test_the_chat_survives_the_three_failures(self) -> None:
        _, checks, _ = evaluate(COMPANY_DIR, SilentLLM(), question_filters=["person-surname"], log=lambda _: None)  # type: ignore[arg-type]
        assert [c.ok for c in checks] == [True, True, True]


class TestReport:
    def results(self) -> list[QuestionResult]:
        return [
            QuestionResult("q-a", "date", "¿a?", 5, 3, 3, 2, 1, 1, 1, 0, 1, False, 1.5, "resp a", {"missing": ["c1 X -> Y: algo (sin fecha)"], "extra": ["c9 Z -> W: otro (2026-01-01)"]}),
            QuestionResult("q-b", "date", "¿b?", 2, 0, 2, 0, 0, 0, 0, 0, 0, True, 0.5, "resp b", {}),
        ]

    def test_totals_add_up_counts(self) -> None:
        t = totals(self.results())
        assert (t.questions, t.needed, t.said, t.missing, t.extra, t.wrong_people, t.wrong_due, t.invented, t.degraded) == (2, 7, 5, 2, 1, 1, 1, 1, 1)

    def test_the_report_has_a_row_per_category_a_total_and_the_questions_with_something_wrong(self) -> None:
        report = format_report(self.results(), [], show=False)
        assert "TOTAL" in report and "q-a" in report and "q-b" in report and "resp a" not in report

    def test_show_adds_the_answers_and_what_was_wrong(self) -> None:
        report = format_report(self.results(), [], show=True)
        assert "resp a" in report and "-- missing:" in report and "c1 X -> Y" in report and "-- extra:" in report

    def test_the_results_can_be_written_as_json(self) -> None:
        assert json.loads(json.dumps([asdict(r) for r in self.results()]))[0]["name"] == "q-a"
