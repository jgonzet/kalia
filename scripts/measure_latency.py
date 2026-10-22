"""Measure how long the chat takes to answer and how much the model writes, and print a report for docs/MEASUREMENTS.md.

Every question goes through `POST /chat` (retrieval plus the answerer's LLM, as a person using the app would), so the time is
what that person waits. It needs a real LLM; the tokens are reported only by Ollama (the other backends give seconds only).

    uv run scripts/measure_latency.py                                   the whole chat bank of lamanija
    uv run scripts/measure_latency.py --ask "¿Cómo viene todo?" --repeat 12    one question, twelve times
    uv run scripts/measure_latency.py --limit 8 --json runs/latency.json       a few questions, and the raw rows

The LLM is the answerer's (`ANSWERER_LLM_*` if set, else `LLM_*`). Before measuring, one short call loads the model, so the
first question is not paying for it; `--cold` skips it (unload the model first to measure a cold start).
Paste the report at the end of docs/MEASUREMENTS.md, or into an issue if you are reporting your own numbers.
"""

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make `app` importable

import run_log  # noqa: E402  (scripts/ is already on sys.path when this file is run)
from app.config import Settings  # noqa: E402
from app.llm import LLMClient, build_llm  # noqa: E402
from app.main import create_app  # noqa: E402
from chat_bank import BANK_FILE, latest, read_bank  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

GPU_SAMPLE_SECONDS = 2
SLOWEST_SHOWN = 5


class Question(TypedDict):
    id: str
    version: str
    text: str


class Sample(TypedDict):
    id: str
    question: str
    seconds: float
    commitments: int  # how many the retrieval handed to the LLM
    degraded: bool  # the chat came back without the LLM's answer (it failed, timed out or the prompt did not fit)
    prompt_tokens: int | None  # None where the backend does not report tokens
    answer_tokens: int | None
    answer_seconds: float | None


class GpuSummary(TypedDict):
    samples: int
    max_temperature: float
    max_power: float
    thermal_slowdown: int  # samples with the "SW thermal slowdown" reason active
    power_cap: int
    power_brake: int


class _TimedLLM:
    """Wraps the LLM of the chat to time each call and keep the tokens Ollama reports."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self.seconds = 0.0

    def complete(self, prompt: str) -> str:
        started = time.monotonic()
        try:
            return self._llm.complete(prompt)
        finally:
            self.seconds = time.monotonic() - started

    @property
    def stats(self) -> dict[str, float | int | str] | None:
        """What the wrapped client reported about its last call, if it reports anything (Ollama does)."""
        return getattr(self._llm, "last_stats", None)


class _GpuSampler(threading.Thread):
    """Reads `nvidia-smi` every few seconds in the background; it stays silent when there is no NVIDIA GPU."""

    QUERY = "temperature.gpu,power.draw,clocks_throttle_reasons.sw_thermal_slowdown,clocks_throttle_reasons.sw_power_cap,clocks_throttle_reasons.hw_power_brake_slowdown"

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self.rows: list[list[str]] = []

    def run(self) -> None:
        while not self._stop_event.is_set():
            row = _nvidia_smi(self.QUERY)
            if row is None:
                return
            self.rows.append([cell.strip() for cell in row.split(",")])
            self._stop_event.wait(GPU_SAMPLE_SECONDS)

    def stop(self) -> GpuSummary | None:
        self._stop_event.set()
        self.join(timeout=5)
        if not self.rows:
            return None
        return GpuSummary(
            samples=len(self.rows),
            max_temperature=max(float(r[0]) for r in self.rows),
            max_power=max(float(r[1].split()[0]) for r in self.rows),
            thermal_slowdown=sum(r[2] == "Active" for r in self.rows),
            power_cap=sum(r[3] == "Active" for r in self.rows),
            power_brake=sum(r[4] == "Active" for r in self.rows),
        )


def _nvidia_smi(query: str) -> str | None:
    """Return the first line `nvidia-smi` prints for the query, or None if the tool or the GPU is not there."""
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader"], capture_output=True, text=True, timeout=10, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return out.splitlines()[0] if out.strip() else None


def percentile(values: list[float], fraction: float) -> float:
    """Return the nearest-rank percentile (`fraction` 0.9 is the p90) of a non-empty list."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def machine_description() -> list[str]:
    """Describe the machine: GPU, CPU, memory and whether it is plugged in; "unknown" for what it cannot read."""
    gpu = _nvidia_smi("name,driver_version,memory.total")
    cpu = ram = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                ram = f"{int(line.split()[1]) / 1024 / 1024:.0f} GiB"
                break
    except OSError:
        pass
    power = "unknown"
    mains = [p for p in Path("/sys/class/power_supply").glob("*") if (p / "type").exists() and (p / "type").read_text().strip() == "Mains"]
    if mains:
        power = "charger connected" if any((p / "online").read_text().strip() == "1" for p in mains) else "on battery"
    return [
        f"GPU: {gpu or 'none detected (nvidia-smi not available)'}",
        f"CPU: {cpu}",
        f"RAM: {ram}",
        f"Power: {power}",
        f"OS: {platform.system()} {platform.release()}",
    ]


def read_questions(company_dir: Path, asked: list[str] | None, repeat: int, limit: int | None) -> list[Question]:
    """Return the questions to ask: the ones given with --ask, or the latest version of each question of the chat bank."""
    if asked:
        questions = [Question(id=f"ask-{n + 1}", version="-", text=text) for n, text in enumerate(asked)]
    else:
        questions = [Question(id=r["id"], version=r["version"], text=r["question"]) for r in latest(read_bank(company_dir / BANK_FILE))]
    return (questions * repeat)[:limit]


def questions_hash(questions: list[Question]) -> str:
    """Return a short fingerprint of the questions asked (id, version, text and order), to know two runs asked the same."""
    text = "\n".join(f"{q['id']}\t{q['version']}\t{q['text']}" for q in questions)
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def measure(
    questions: list[Question], settings: Settings, llm: _TimedLLM, warm_up: bool
) -> tuple[list[Sample], GpuSummary | None]:
    """Ask every question through POST /chat and return what each took, plus a summary of the GPU while it ran."""
    with tempfile.TemporaryDirectory() as tmp:
        client = TestClient(create_app(replace(settings, db_path=str(Path(tmp) / "latency.db")), llm=llm))
        if warm_up:
            llm.complete("Responde solo: OK")
        sampler = _GpuSampler()
        sampler.start()
        samples: list[Sample] = []
        for n, question in enumerate(questions, 1):
            started = time.monotonic()
            body = client.post("/chat", json={"question": question["text"]}).json()
            stats = llm.stats
            sample = Sample(
                id=question["id"],
                question=question["text"],
                seconds=round(time.monotonic() - started, 2),
                commitments=len(body["commitments"]),
                degraded=body["degraded"],
                prompt_tokens=int(stats["prompt_tokens"]) if stats else None,
                answer_tokens=int(stats["answer_tokens"]) if stats else None,
                answer_seconds=float(stats["answer_seconds"]) if stats else None,
            )
            samples.append(sample)
            print(f"{n}/{len(questions)} {sample['id']}: {sample['seconds']} s, {sample['answer_tokens']} tokens", file=sys.stderr, flush=True)
        return samples, sampler.stop()


def report(
    samples: list[Sample],
    gpu: GpuSummary | None,
    questions: list[Question],
    settings: Settings,
    args: argparse.Namespace,
    title: str,
) -> str:
    """Build the report in the format of docs/MEASUREMENTS.md."""
    llm = settings.llm_for("answerer")
    git = run_log.git_state()
    seconds = [s["seconds"] for s in samples]
    tokens = [s["answer_tokens"] for s in samples if s["answer_tokens"] is not None]
    speeds = [s["answer_tokens"] / s["answer_seconds"] for s in samples if s["answer_tokens"] and s["answer_seconds"]]
    if args.ask:
        source = "asked with --ask: " + "; ".join(f"`{q}`" for q in args.ask)
    else:
        source = f"`data/{args.company}/{BANK_FILE}` (latest version of each question)"
    lines = [
        f"### {date.today().isoformat()} — {title}",
        "",
        f"**Commit:** {git['commit']}{' (with uncommitted changes)' if git['dirty'] else ''}",
        "",
        "**Machine**",
        *[f"- {line}" for line in machine_description()],
        "",
        "**Configuration** (the answerer's LLM)",
        f"- Backend: {llm.backend}; model: {llm.model}",
        f"- Context window: {llm.context_tokens or 'not set'} tokens; timeout: {llm.timeout_seconds:g} s per attempt",
        "",
        "**Method**",
        f"- Command: `uv run scripts/measure_latency.py {' '.join(sys.argv[1:])}`".rstrip(),
        f"- Questions: {len(questions)} from {source}, fingerprint `{questions_hash(questions)}`",
        f"- Warm-up before measuring: {'no (cold start)' if args.cold else 'yes'}",
        "",
        "**Results**",
        "",
        "| | median | p90 | max |",
        "|---|---|---|---|",
        f"| Seconds per answer | {statistics.median(seconds):.1f} | {percentile(seconds, 0.9):.1f} | {max(seconds):.1f} |",
    ]
    if tokens:
        lines.append(f"| Tokens written | {statistics.median(tokens):.0f} | {percentile([float(t) for t in tokens], 0.9):.0f} | {max(tokens)} |")
    else:
        lines.append("| Tokens written | n/a | n/a | n/a |")
    lines.append("")
    if speeds:
        lines.append(f"- Writing speed: median {statistics.median(speeds):.1f} tokens/s, minimum {min(speeds):.1f}")
    else:
        lines.append("- Writing speed: n/a (this backend does not report tokens)")
    over = sum(s > llm.timeout_seconds for s in seconds)
    lines += [
        f"- Answers that came back degraded: {sum(s['degraded'] for s in samples)} of {len(samples)}",
        f"- Answers over 60 s: {sum(s > 60 for s in seconds)}; over 120 s: {sum(s > 120 for s in seconds)}; over the timeout: {over}",
    ]
    if gpu:
        lines.append(
            f"- GPU while measuring ({gpu['samples']} samples, every {GPU_SAMPLE_SECONDS} s): up to {gpu['max_temperature']:.0f} °C and "
            f"{gpu['max_power']:.0f} W; thermal slowdown in {gpu['thermal_slowdown']}, power cap in {gpu['power_cap']}, "
            f"power brake in {gpu['power_brake']} of the samples"
        )
    lines += ["", f"Slowest {SLOWEST_SHOWN}:", "", "| Question | seconds | tokens written | commitments given |", "|---|---|---|---|"]
    for s in sorted(samples, key=lambda x: -x["seconds"])[:SLOWEST_SHOWN]:
        lines.append(f"| {s['id']} | {s['seconds']} | {s['answer_tokens'] if s['answer_tokens'] is not None else 'n/a'} | {s['commitments']} |")
    lines += ["", "**Observations:** _to fill in by hand_", ""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company", nargs="?", default="lamanija", help="dataset whose sample is loaded and whose chat bank is asked (default: lamanija)")
    parser.add_argument("--ask", action="append", help="ask this text instead of the chat bank (repeatable)")
    parser.add_argument("--repeat", type=int, default=1, help="ask the whole list this many times (default 1)")
    parser.add_argument("--limit", type=int, help="ask only the first N questions of the list")
    parser.add_argument("--cold", action="store_true", help="no warm-up call: the first question pays for loading the model")
    parser.add_argument("--title", help="title of the report (default: the backend and the model)")
    parser.add_argument("--json", type=Path, help="also write the raw rows to this file")
    args = parser.parse_args(argv)

    company_dir = ROOT / "data" / args.company
    if not (company_dir / "company.json").is_file():
        print(f"no dataset at {company_dir}")
        return 1
    settings = replace(Settings.from_env(), sample_company=args.company)
    llm_settings = settings.llm_for("answerer")
    if llm_settings.backend == "fake":
        print("The backend of the answerer is fake: there is no LLM to measure.")
        return 1
    questions = read_questions(company_dir, args.ask, args.repeat, args.limit)
    if not questions:
        print("no questions to ask")
        return 1
    llm = _TimedLLM(build_llm(llm_settings))
    samples, gpu = measure(questions, settings, llm, warm_up=not args.cold)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report(samples, gpu, questions, settings, args, args.title or f"Chat latency, {llm_settings.backend} {llm_settings.model}"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
