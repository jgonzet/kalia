"""Append-only log of evaluation runs, to trace metrics over time. See README ("Evaluate the retrieval").

Evaluation scripts call `append_run`; this file also lists what was logged:

    uv run scripts/run_log.py                       every logged run, oldest first
    uv run scripts/run_log.py --stage retrieval     only the runs of one stage

One JSON object per line in `runs/metrics.jsonl` (git-ignored). `params` and `metrics` are flat, like the
ones MLflow logs, so moving the history there later is mechanical.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = ROOT / "runs" / "metrics.jsonl"


class GitState(TypedDict):
    commit: str
    dirty: bool  # True when there were uncommitted changes, so the commit alone does not identify the code


class RunRecord(TypedDict):
    timestamp: str
    stage: str  # "retrieval", later "extraction" or "chat"
    git: GitState
    params: dict[str, str | int | float]  # what was tried: retriever, model, prompt hash, dataset, questions version
    metrics: dict[str, float]  # totals of the run
    details: dict[str, dict[str, float]]  # the same metrics per item (question, document)


def git_state() -> GitState:
    """Return the short HEAD commit and whether the working tree had uncommitted changes."""
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return GitState(commit=commit, dirty=bool(status.strip()))


def append_run(
    stage: str,
    params: dict[str, str | int | float],
    metrics: dict[str, float],
    details: dict[str, dict[str, float]],
    path: Path = DEFAULT_LOG,
) -> RunRecord:
    """Add one run to the log (creating the file and its folder if needed) and return the record."""
    record = RunRecord(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        stage=stage,
        git=git_state(),
        params=params,
        metrics=metrics,
        details=details,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_runs(path: Path = DEFAULT_LOG) -> list[RunRecord]:
    """Return the logged runs, oldest first; an absent file means no runs."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _format_number(value: float) -> str:
    return f"{value:.3f}" if isinstance(value, float) and not value.is_integer() else f"{value:g}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", help="only the runs of this stage")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args(argv)

    runs = [r for r in read_runs(args.log) if not args.stage or r["stage"] == args.stage]
    if not runs:
        print(f"no runs logged in {args.log}")
        return 0
    for run in runs:
        commit = run["git"]["commit"] + ("*" if run["git"]["dirty"] else "")
        params = " ".join(f"{k}={v}" for k, v in run["params"].items())
        metrics = " ".join(f"{k}={_format_number(v)}" for k, v in run["metrics"].items())
        print(f"{run['timestamp']}  {run['stage']:<10}  {commit:<9}  {params}")
        print(f"    {metrics}")
    print("\n* = uncommitted changes when the run was made")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
