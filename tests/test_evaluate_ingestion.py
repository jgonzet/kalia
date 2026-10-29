import json
from collections.abc import Callable
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

import run_log
from app.config import Settings
from app.ingestion.dataset import DatasetSource
from app.llm import LLMError
from app.models import Catalog, Commitment, Document
from evaluate_extraction import load_answer_keys
from evaluate_ingestion import (
    Outcome,
    Reading,
    acceptance_questions,
    base_documents,
    chat_stages,
    document_of,
    log_run,
    run_check,
    storage_stage,
)

ROOT = Path(__file__).resolve().parent.parent
COMPANY_DIR = ROOT / "data" / "lamanija"
OWNER = "evaluation"
NEW = "lamanija-0025"
Tweak = Callable[[list[Commitment]], list[Commitment]]


class EchoLLM:
    """Answers with the whole prompt, so every commitment it was given 'appears' in the answer."""

    def complete(self, prompt: str) -> str:
        return prompt


class SilentLLM:
    def complete(self, prompt: str) -> str:
        return "no sé"


class ScriptedExtractor:
    """Returns the commitments of the `expected` file of each document, with the errors a test asks for."""

    def __init__(self, tweaks: dict[str, Tweak] | None = None, failing: set[str] | None = None) -> None:
        self._catalog = DatasetSource(COMPANY_DIR).catalog()
        self._keys = load_answer_keys(COMPANY_DIR, self._catalog)
        self._tweaks = tweaks or {}
        self._failing = failing or set()

    def extract(self, document: Document, catalog: Catalog) -> list[Commitment]:
        if document.id in self._failing:
            raise LLMError("down")
        commitments = [
            Commitment(e.id, OWNER, e.who_id, e.to_whom_id, e.what, e.due, e.project_id, document.id, document.date)
            for e in self._keys[document.id].commitments
        ]
        return self._tweaks.get(document.id, lambda c: c)(commitments)


def run(extractor: ScriptedExtractor | None = None, llm: object | None = None) -> Outcome:
    settings = Settings(llm_backend="fake", owner_id=OWNER)
    return run_check(COMPANY_DIR, extractor or ScriptedExtractor(), llm or EchoLLM(), settings, log=lambda _: None)  # type: ignore[arg-type]


def by_id(outcome: Outcome) -> dict[str, "object"]:
    return {q.id: q for q in outcome.questions}


def commitment(id: str, document: str = "doc-1", who: str = "p1", to_whom: str = "p2", what: str = "hacer algo", due: date | None = None) -> Commitment:
    return Commitment(id, OWNER, who, to_whom, what, due, None, document, date(2026, 10, 1))


class TestFaithfulRun:
    def test_nothing_is_lost_or_added_at_any_stage(self) -> None:
        outcome = run()
        assert not outcome.base_failed and not outcome.extraction_failed
        assert (len(outcome.extraction.missing), len(outcome.extraction.extra)) == (0, 0)
        assert outcome.extraction.expected == len(outcome.extraction.matches) == 2
        assert (outcome.storage.others_changed, outcome.storage.new_lost) == (0, 0)
        assert len(outcome.questions) == 2
        for q in outcome.questions:
            assert q.before.retrieved == 0 and q.before.retrieval_added == 0
            assert q.after.wanted == q.expected_new > 0
            assert (q.after.retrieval_lost, q.after.retrieval_added, q.after.answer_lost) == (0, 0, 0)
            assert q.after.said == q.after.wanted

    def test_the_questions_and_the_base_come_from_the_dataset(self) -> None:
        questions, new_document = acceptance_questions(COMPANY_DIR)
        base = base_documents(questions, new_document)
        assert new_document == NEW and NEW not in base
        assert {q["id"] for q in questions} == {"q5-jefe", "q5-semana"}
        assert 0 < len(base) < 24

    def test_a_document_id_comes_from_a_commitment_id(self) -> None:
        assert document_of("lamanija-0025-c2") == NEW


class TestExtractionStage:
    def test_a_commitment_the_extractor_misses_is_not_blamed_on_retrieval_or_answer(self) -> None:
        outcome = run(ScriptedExtractor({NEW: lambda c: c[1:]}))  # drops lamanija-0025-c1
        assert len(outcome.extraction.missing) == 1
        for q in outcome.questions:
            assert (q.after.retrieval_lost, q.after.answer_lost) == (0, 0)
        assert by_id(outcome)["q5-semana"].after.wanted == 0  # type: ignore[attr-defined]

    def test_an_extra_commitment_shows_in_extraction_and_in_retrieval_not_in_storage(self) -> None:
        catalog = DatasetSource(COMPANY_DIR).catalog()
        used = {p for e in load_answer_keys(COMPANY_DIR, catalog)[NEW].commitments for p in (e.who_id, e.to_whom_id)}
        a, b = [p.id for p in catalog.people if p.id not in used][:2]
        extra = lambda c: c + [replace(c[0], id=f"{NEW}-c9", who_id=a, to_whom_id=b, what="algo que nadie prometió")]  # noqa: E731
        outcome = run(ScriptedExtractor({NEW: extra}))
        assert len(outcome.extraction.extra) == 1 and not outcome.extraction.missing
        assert outcome.storage.new_lost == 0 and outcome.storage.returned == outcome.storage.stored == 3
        jefe = by_id(outcome)["q5-jefe"]
        assert jefe.after.retrieval_lost == 0  # type: ignore[attr-defined]

    def test_a_wrong_due_date_shows_in_extraction_and_takes_the_commitment_out_of_the_week(self) -> None:
        later: Tweak = lambda c: [replace(c[0], due=c[0].due + timedelta(days=365)), *c[1:]]  # type: ignore[operator]  # noqa: E731
        outcome = run(ScriptedExtractor({NEW: later}))
        assert sum(not m.due_ok for m in outcome.extraction.matches) == 1
        assert by_id(outcome)["q5-semana"].after.retrieval_lost == 1  # type: ignore[attr-defined]
        assert by_id(outcome)["q5-jefe"].after.retrieval_lost == 0  # type: ignore[attr-defined]

    def test_a_failed_extraction_of_the_new_document_counts_everything_as_missing_and_stores_nothing(self) -> None:
        outcome = run(ScriptedExtractor(failing={NEW}))
        assert outcome.extraction_failed
        assert len(outcome.extraction.missing) == outcome.extraction.expected == 2
        assert outcome.storage.stored == 0 and outcome.storage.others_changed == 0
        assert all(q.after.wanted == 0 and q.after.retrieval_lost == 0 for q in outcome.questions)

    def test_a_base_document_that_fails_is_listed(self) -> None:
        questions, new_document = acceptance_questions(COMPANY_DIR)
        broken = base_documents(questions, new_document)[0]
        outcome = run(ScriptedExtractor(failing={broken}))
        assert outcome.base_failed == [broken] and not outcome.extraction_failed


class TestAnswerStage:
    def test_an_answer_that_leaves_out_what_was_retrieved_is_blamed_on_the_answer_only(self) -> None:
        outcome = run(llm=SilentLLM())
        for q in outcome.questions:
            assert q.after.retrieval_lost == 0
            assert q.after.said == 0 and q.after.answer_lost == q.after.wanted > 0
            assert not q.after.degraded

    def test_an_llm_that_does_not_answer_marks_the_readings_degraded(self) -> None:
        class Broken:
            def complete(self, prompt: str) -> str:
                raise LLMError("down")

        outcome = run(llm=Broken())
        assert all(q.before.degraded and q.after.degraded for q in outcome.questions)
        assert all(q.after.answer_lost == 0 and q.after.retrieved == q.after.wanted for q in outcome.questions)


class TestStages:
    def test_storage_notices_a_commitment_of_another_document_that_vanished_or_changed(self) -> None:
        before = [commitment("a-c1", "a"), commitment("b-c1", "b")]
        after = [commitment("a-c1", "a"), commitment("b-c1", "b", what="otra cosa"), commitment(f"{NEW}-c1", NEW)]
        stage = storage_stage(before, after, [commitment(f"{NEW}-c1", NEW)], NEW)
        assert (stage.others_before, stage.others_changed, stage.stored, stage.new_lost) == (2, 2, 1, 0)

    def test_storage_notices_what_the_extractor_returned_and_was_not_stored(self) -> None:
        returned = [commitment(f"{NEW}-c1", NEW), commitment(f"{NEW}-c2", NEW)]
        stage = storage_stage([], returned[:1], returned, NEW)
        assert (stage.returned, stage.stored, stage.new_lost) == (2, 1, 1)

    def test_a_wanted_commitment_that_is_not_retrieved_is_lost_in_retrieval(self) -> None:
        stored = {c.id: c for c in (commitment("a-c1", "a"), commitment(f"{NEW}-c1", NEW), commitment(f"{NEW}-c2", NEW))}
        reading = Reading("- hacer algo", False, ("a-c1", f"{NEW}-c1"), 0.0)
        stages = chat_stages(reading, stored, {f"{NEW}-c1", f"{NEW}-c2"}, NEW, {"p1": "Ana", "p2": "Beto"}, None, 2026)
        assert (stages.wanted, stages.retrieved, stages.retrieval_lost, stages.retrieval_added) == (2, 1, 1, 0)

    def test_a_degraded_reading_measures_no_answer(self) -> None:
        stored = {f"{NEW}-c1": commitment(f"{NEW}-c1", NEW)}
        reading = Reading("fixed text", True, (f"{NEW}-c1",), 0.0)
        stages = chat_stages(reading, stored, {f"{NEW}-c1"}, NEW, {"p1": "Ana", "p2": "Beto"}, None, 2026)
        assert stages.degraded and (stages.said, stages.answer_lost, stages.invented) == (0, 0, 0)


class TestLogRun:
    def test_the_run_keeps_both_models_and_the_totals_of_each_stage(self, tmp_path: Path) -> None:
        log = tmp_path / "metrics.jsonl"
        record = log_run(run(), "lamanija", "extractor-x", "answerer-y", "v1", path=log)
        assert record["stage"] == "ingestion"
        assert record["params"]["extractor_model"] == "extractor-x" and record["params"]["answerer_model"] == "answerer-y"
        assert {"extraction_missing", "storage_others_changed", "retrieval_lost", "answer_lost"} <= set(record["metrics"])
        assert set(record["details"]) == {f"extraction:{NEW}", "q5-jefe", "q5-semana"}
        assert json.loads(log.read_text(encoding="utf-8").splitlines()[0])["metrics"] == record["metrics"]
        assert run_log.read_runs(log)[0]["stage"] == "ingestion"
