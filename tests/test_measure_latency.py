"""Tests of the latency script (scripts/quality/evals/measure_latency.py) with a fake LLM; the GPU and the machine are not read."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

import pytest

import scripts.quality.evals.measure_latency as ml
from app.config import ROOT, Settings
from app.llm import LLMError

COMPANY_DIR = ROOT / "data" / "lamanija"


class StatsLLM:
    """Answers a fixed text and reports tokens like Ollama does; fails when told to."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.last_stats: dict[str, float | int | str] | None = None
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.fail:
            raise LLMError("stub failure")
        self.last_stats = {"prompt_tokens": 100, "answer_tokens": 50, "answer_seconds": 2.0, "done_reason": "stop"}
        return "answer"


@pytest.fixture(autouse=True)
def no_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ml, "_nvidia_smi", lambda query: None)
    monkeypatch.setattr(ml, "machine_description", lambda: ["GPU: test"])


def settings() -> Settings:
    return replace(Settings(), llm_backend="ollama", sample_company="lamanija", commitments_source="saved", reference_date=None)


def questions(*texts: str) -> list[ml.Question]:
    return [ml.Question(id=f"q{n}", version="1", text=text) for n, text in enumerate(texts, 1)]


def args(**overrides: object) -> argparse.Namespace:
    return argparse.Namespace(**{"ask": None, "company": "lamanija", "cold": False, **overrides})


def test_percentile_is_the_nearest_rank() -> None:
    values = [float(n) for n in range(1, 11)]
    assert ml.percentile(values, 0.9) == 9.0
    assert ml.percentile(values, 0.5) == 5.0
    assert ml.percentile(values, 1.0) == 10.0
    assert ml.percentile([4.0, 1.0, 3.0, 2.0], 0.5) == 2.0  # it sorts first
    assert ml.percentile([7.5], 0.9) == 7.5


def test_the_fingerprint_changes_with_text_version_and_order() -> None:
    base = questions("a", "b")
    assert ml.questions_hash(base) == ml.questions_hash(questions("a", "b"))
    assert len(ml.questions_hash(base)) == 12
    assert ml.questions_hash(base) != ml.questions_hash(questions("b", "a"))
    assert ml.questions_hash(base) != ml.questions_hash(questions("a", "c"))
    assert ml.questions_hash(base) != ml.questions_hash([ml.Question(id="q1", version="2", text="a"), base[1]])


def test_questions_come_from_ask_or_from_the_latest_bank_versions_repeated_and_limited() -> None:
    asked = ml.read_questions(COMPANY_DIR, ["x", "y"], repeat=2, limit=3)
    assert [(q["id"], q["text"]) for q in asked] == [("ask-1", "x"), ("ask-2", "y"), ("ask-1", "x")]
    bank = ml.read_questions(COMPANY_DIR, None, repeat=1, limit=None)
    assert bank and len({q["id"] for q in bank}) == len(bank)
    assert len(ml.read_questions(COMPANY_DIR, None, repeat=2, limit=None)) == 2 * len(bank)


def test_the_timed_llm_keeps_the_tokens_and_times_a_failed_call() -> None:
    timed = ml._TimedLLM(StatsLLM())
    assert timed.stats is None and timed.complete("p") == "answer"
    assert timed.seconds >= 0 and timed.stats and timed.stats["answer_tokens"] == 50
    failing = ml._TimedLLM(StatsLLM(fail=True))
    with pytest.raises(LLMError):
        failing.complete("p")
    assert failing.seconds >= 0


def test_measure_asks_every_question_through_the_chat_and_warms_up_once() -> None:
    llm = StatsLLM()
    samples, gpu = ml.measure(questions("¿Cómo viene todo?", "¿Qué debo?"), settings(), ml._TimedLLM(llm), warm_up=True)
    assert gpu is None  # no nvidia-smi
    assert [s["id"] for s in samples] == ["q1", "q2"]
    assert all(s["answer_tokens"] == 50 and s["answer_seconds"] == 2.0 and not s["degraded"] for s in samples)
    assert all(s["commitments"] > 0 for s in samples)
    assert llm.calls == 1 + 2  # the warm-up and the two questions


def test_a_failing_llm_gives_degraded_samples_without_tokens() -> None:
    samples, _ = ml.measure(questions("¿Cómo viene todo?"), settings(), ml._TimedLLM(StatsLLM(fail=True)), warm_up=False)
    assert samples[0]["degraded"] is True
    assert samples[0]["answer_tokens"] is None and samples[0]["answer_seconds"] is None


def sample(id: str, seconds: float, tokens: int | None = 50, answer_seconds: float | None = 2.0, degraded: bool = False) -> ml.Sample:
    return ml.Sample(
        id=id, question="?", seconds=seconds, commitments=3, degraded=degraded, prompt_tokens=100 if tokens else None, answer_tokens=tokens, answer_seconds=answer_seconds
    )


def test_the_report_has_the_numbers_of_the_samples() -> None:
    samples = [sample("q1", 10.0), sample("q2", 20.0, tokens=100, answer_seconds=2.0), sample("q3", 70.0, degraded=True), sample("q4", 130.0)]
    gpu = ml.GpuSummary(samples=4, max_temperature=81.0, max_power=140.2, thermal_slowdown=1, power_cap=0, power_brake=0)
    text = ml.report(samples, gpu, questions("a", "b", "c", "d"), settings(), args(), "My title")
    assert "up to 81 °C and 140 W; thermal slowdown in 1" in text
    assert "My title" in text and "- GPU: test" in text
    assert "| Seconds per answer | 45.0 | 130.0 | 130.0 |" in text  # median of 10, 20, 70, 130
    assert "| Tokens written | 50 | 100 | 100 |" in text
    assert "Writing speed: median 25.0 tokens/s, minimum 25.0" in text
    assert "degraded: 1 of 4" in text
    assert "over 60 s: 2; over 120 s: 1; over the timeout: 1" in text  # the default timeout is 120 s
    assert f"fingerprint `{ml.questions_hash(questions('a', 'b', 'c', 'd'))}`" in text
    assert "Warm-up before measuring: yes" in text
    assert text.index("| q4 |") < text.index("| q3 |") < text.index("| q2 |")  # slowest first


def test_the_report_without_tokens_says_so() -> None:
    text = ml.report([sample("q1", 5.0, tokens=None, answer_seconds=None)], None, questions("a"), settings(), args(cold=True), "t")
    assert "| Tokens written | n/a | n/a | n/a |" in text
    assert "Writing speed: n/a" in text
    assert "no (cold start)" in text


def test_main_refuses_a_fake_backend_and_a_missing_dataset(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("app.config.ENV_FILES", ())
    monkeypatch.setenv("LLM_BACKEND", "fake")
    assert ml.main([]) == 1
    assert "fake" in capsys.readouterr().out
    assert ml.main(["no-such-company"]) == 1
    assert "no dataset" in capsys.readouterr().out


def test_main_prints_the_report_and_writes_the_rows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("app.config.ENV_FILES", ())
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setattr(ml, "build_llm", lambda llm_settings: StatsLLM())
    rows = tmp_path / "out" / "rows.json"
    assert ml.main(["--ask", "¿Cómo viene todo?", "--json", str(rows), "--title", "Test run"]) == 0
    out = capsys.readouterr().out
    assert "Test run" in out and "**Results**" in out
    assert json.loads(rows.read_text(encoding="utf-8"))[0]["answer_tokens"] == 50
