import json
from datetime import date
from pathlib import Path

import pytest

from app.answering.llm_answerer import DEGRADED_TEXT
from app.ingestion.dataset import DatasetSource
from app.llm import LLMError
from app.models import Commitment
from app.storage.sqlite import SqliteStore
from evaluate_chat import (
    QuestionResult,
    content_words,
    evaluate,
    find_needed,
    format_report,
    is_in_answer,
    totals,
)
from evaluate_extraction import AnswerKey, Expected
from evaluate_retrieval import OWNER_ID, build_store

ROOT = Path(__file__).resolve().parent.parent
COMPANY_DIR = ROOT / "data" / "lamanija"


def stored(id: str, what: str, who: str = "p1", to_whom: str = "p2", due: date | None = None, document: str = "d1") -> Commitment:
    return Commitment(id, "o", who, to_whom, what, due, None, document, date(2026, 1, 1))


class TestIsInAnswer:
    def test_words_are_compared_without_case_or_accents(self) -> None:
        assert is_in_answer(stored("a", "Armar la propuesta de reconexión"), "ARMAR la PROPUESTA de reconexion")

    def test_short_words_do_not_count(self) -> None:
        assert content_words("a la de un plan") == {"plan"}

    def test_half_of_the_words_is_enough_less_is_not(self) -> None:
        commitment = stored("a", "pasar informe estado festival")
        assert is_in_answer(commitment, "el informe y el festival")
        assert not is_in_answer(commitment, "el informe")

    def test_a_commitment_with_no_content_words_is_never_found(self) -> None:
        assert not is_in_answer(stored("a", "ir a ver"), "ir a ver")


class TestFindNeeded:
    KEYS = {
        "d1": AnswerKey(
            "d1",
            (
                Expected("d1-c1", "p1", "p2", "mandar el informe", date(2026, 2, 1), None),
                Expected("d1-c2", "p2", "p1", "revisar el plan", None, None),
            ),
            (),
        )
    }

    def test_pairs_by_content_and_ignores_the_stored_ids(self) -> None:
        extracted = [stored("zzz-1", "Mandar el informe", due=date(2026, 2, 1))]
        needed, lost = find_needed(["d1-c1"], self.KEYS, extracted)
        assert [c.id for c in needed] == ["zzz-1"] and lost == []

    def test_an_expected_commitment_that_was_not_extracted_is_lost(self) -> None:
        needed, lost = find_needed(["d1-c1", "d1-c2"], self.KEYS, [stored("x", "Mandar el informe", due=date(2026, 2, 1))])
        assert len(needed) == 1 and lost == ["d1-c2"]

    def test_a_document_without_an_answer_key_is_lost(self) -> None:
        needed, lost = find_needed(["other-c1"], self.KEYS, [])
        assert needed == [] and lost == ["other-c1"]

    def test_the_same_people_with_another_due_date_still_pair(self) -> None:
        needed, _ = find_needed(["d1-c1"], self.KEYS, [stored("x", "Mandar el informe", due=date(2026, 3, 1))])
        assert len(needed) == 1


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


class NoCommitmentsLLM:
    """For the extraction of the held-out document: finds nothing."""

    def complete(self, prompt: str) -> str:
        return "[]"


@pytest.fixture(scope="module")
def database(tmp_path_factory: pytest.TempPathFactory) -> str:
    """A database built from the `expected` files, as the retrieval evaluation does (the held-out document left out)."""
    source = DatasetSource(COMPANY_DIR)
    path = str(tmp_path_factory.mktemp("chat") / "base.db")
    build_store(path, COMPANY_DIR, source.catalog(), False, set(source.company["held_out"]))
    return path


def run(database: str, llm: object, extraction_llm: object = NoCommitmentsLLM(), questions: list[str] | None = None) -> list[QuestionResult]:
    return evaluate(COMPANY_DIR, database, OWNER_ID, llm, extraction_llm, question_ids=questions, log=lambda _: None)  # type: ignore[arg-type]


class TestEvaluate:
    def test_an_answer_with_everything_the_retriever_brought_has_every_needed_commitment(self, database: str) -> None:
        results = run(database, EchoLLM())
        assert results and all(r.needed_in_answer == r.needed_retrieved for r in results)
        assert all(r.omitted == [] for r in results)

    def test_an_answer_with_nothing_omits_everything_that_was_needed(self, database: str) -> None:
        results = run(database, SilentLLM())
        assert all(r.needed_in_answer == 0 and r.extra_in_answer == 0 for r in results)
        assert all(len(r.omitted) == r.needed_retrieved for r in results)

    def test_a_broken_llm_marks_every_question_degraded(self, database: str) -> None:
        results = run(database, BrokenLLM())
        assert all(r.degraded and r.answer == DEGRADED_TEXT for r in results)

    def test_the_commitments_of_the_database_are_all_found_so_nothing_is_lost_before_the_held_out_document(self, database: str) -> None:
        results = {r.name: r for r in run(database, SilentLLM())}
        assert results["q1-smithers"].lost_in_extraction == 0

    def test_questions_around_the_held_out_document_are_measured_before_and_after(self, database: str) -> None:
        names = [r.name for r in run(database, SilentLLM())]
        assert "q5-jefe@before" in names and "q5-jefe@after" in names and "q5-jefe" not in names

    def test_if_the_held_out_document_yields_nothing_its_commitments_count_as_lost(self, database: str) -> None:
        results = {r.name: r for r in run(database, SilentLLM())}
        assert results["q5-jefe@before"].lost_in_extraction == 0
        assert results["q5-jefe@after"].lost_in_extraction > 0

    def test_if_the_extraction_of_the_held_out_document_fails_the_after_questions_are_skipped(self, database: str) -> None:
        names = [r.name for r in run(database, SilentLLM(), BrokenLLM())]
        assert "q5-jefe@before" in names and not any(n.endswith("@after") for n in names)

    def test_only_the_asked_questions_are_measured(self, database: str) -> None:
        assert [r.name for r in run(database, SilentLLM(), questions=["q2-semana"])] == ["q2-semana"]

    def test_the_database_it_is_given_is_not_written(self, database: str) -> None:
        before = Path(database).read_bytes()
        run(database, SilentLLM())
        assert Path(database).read_bytes() == before
        assert SqliteStore(database, OWNER_ID).get_document("lamanija-0025") is None

    def test_a_database_without_a_catalog_is_an_error_not_a_crash(self, tmp_path: Path) -> None:
        empty = str(tmp_path / "empty.db")
        SqliteStore(empty, OWNER_ID)
        with pytest.raises(ValueError, match="no catalog"):
            run(empty, SilentLLM())

    def test_a_document_already_in_the_database_has_no_before_so_its_questions_are_skipped(self, tmp_path: Path) -> None:
        source = DatasetSource(COMPANY_DIR)
        path = str(tmp_path / "all.db")
        build_store(path, COMPANY_DIR, source.catalog(), True, set(source.company["held_out"]))
        store = SqliteStore(path, OWNER_ID)
        store.save_document(source.document("lamanija-0025"))
        names = [r.name for r in run(path, SilentLLM())]
        assert not any(n.startswith("q5") for n in names) and "q2-semana" in names


class TestReport:
    def results(self) -> list[QuestionResult]:
        return [
            QuestionResult("q-a", "¿a?", 5, 1, 4, 4, 3, 1, False, 1.5, "resp a", ["c1 X -> Y: algo (no deadline)"], ["c9 Z -> W: otro (2026-01-01)"]),
            QuestionResult("q-b", "¿b?", 2, 0, 2, 2, 2, 0, True, 0.5, "resp b", [], []),
        ]

    def test_totals_add_up_counts(self) -> None:
        t = totals(self.results())
        assert (t.questions, t.expected, t.lost_in_extraction, t.needed_retrieved, t.needed_in_answer, t.extra_in_answer, t.degraded) == (2, 7, 1, 6, 5, 1, 1)

    def test_the_report_has_a_row_per_question_and_a_total(self) -> None:
        report = format_report(self.results(), show=False)
        assert "q-a" in report and "q-b" in report and "TOTAL" in report and "resp a" not in report

    def test_show_adds_the_answers_and_what_was_omitted_or_added(self) -> None:
        report = format_report(self.results(), show=True)
        assert "resp a" in report and "-- omitted:" in report and "c1 X -> Y" in report and "-- extra:" in report and "c9 Z -> W" in report

    def test_the_results_can_be_written_as_json(self) -> None:
        from dataclasses import asdict

        assert json.loads(json.dumps([asdict(r) for r in self.results()]))[0]["name"] == "q-a"
