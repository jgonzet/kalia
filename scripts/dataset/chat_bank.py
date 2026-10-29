"""Build and check the chat bank of a synthetic dataset (`data/<company>/chat_bank.jsonl`).

    uv run scripts/dataset/chat_bank.py lamanija            add the questions of the spec that are not in the file yet
    uv run scripts/dataset/chat_bank.py lamanija --check    only verify the file against the spec and the `expected` files

The chat bank measures what the LLM does with a list of commitments that is already chosen, apart from the retrieval.
Each question gives the LLM a controlled list: the commitments the question needs (`needed`) plus some it does not
(`noise`), and the answer is judged against that. Both sets are computed from conditions over the `expected` files, like
the retrieval bank (`scripts/dataset/retrieval_bank.py`, whose conditions and context this file reuses); the conditions are
written in `scripts/dataset/chat_bank_<company>.py`. Nothing here imports `app/`. Formats and limits: docs/DATASET.md ("Chat bank").

A published question is never edited: if the computed record of a published question stops matching the file, the
script stops and says so; the fix is a new `version` of that question.
"""

import argparse
import importlib
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))  # make `scripts` importable when this file is run by path

from scripts.dataset.retrieval_bank import Cond, Context, Row, load_context, load_rows, load_specs, read_jsonl  # noqa: E402

DATA_DIR = ROOT / "data"
BANK_FILE = "chat_bank.jsonl"
FIRST_VERSION = "v1"
DEFAULT_NOISE_SIZE = 8  # most commitments that are not needed given to the LLM with a question


@dataclass(frozen=True)
class Noise:
    """A kind of commitment the question does not need but a retrieval could let through, and why it is there."""

    reason: str
    cond: Cond


@dataclass(frozen=True)
class ChatSpec:
    """A question of the chat bank, the condition that defines what it needs and the kinds of noise given with it.

    `noise_size` is the most noise commitments given, shared between the kinds of noise; None gives all of them.
    The lists are those of the whole dataset, held-out document included: the LLM gets a list, so whether a document came
    later does not matter to it (the retrieval bank and the acceptance questions are where that is measured).
    """

    id: str
    category: str
    question: str
    needed: Cond
    noise: tuple[Noise, ...] = ()
    version: str = FIRST_VERSION
    noise_size: int | None = DEFAULT_NOISE_SIZE


class ChatRecord(TypedDict):
    """One line of `chat_bank.jsonl`."""

    id: str
    version: str
    category: str
    question: str
    rule: str
    noise_rules: dict[str, str]  # reason -> condition, in words
    needed: list[str]
    noise: dict[str, str]  # commitment id -> the reason it is noise


def read_bank(path: Path) -> list[ChatRecord]:
    """Read the published bank file; an absent file means no questions yet."""
    return cast(list[ChatRecord], read_jsonl(path)) if path.exists() else []


def latest(records: list[ChatRecord]) -> list[ChatRecord]:
    """Keep, for each question id, its highest version."""
    best: dict[str, ChatRecord] = {}
    for record in records:
        if record["id"] not in best or record["version"] > best[record["id"]]["version"]:
            best[record["id"]] = record
    return list(best.values())


def spread(candidates: list[Row], count: int | None) -> list[Row]:
    """Pick `count` of the candidates evenly spaced along the list (all of them if `count` is None or enough is not there)."""
    if count is None or len(candidates) <= count:
        return candidates
    return [candidates[i * len(candidates) // count] for i in range(count)]


def pick_noise(spec: ChatSpec, rows: list[Row]) -> dict[str, str]:
    """Choose the noise of a question: each kind gets an equal share, taken evenly along the commitments in order."""
    needed = {r.id for r in rows if spec.needed.test(r)}
    if not spec.noise or spec.noise_size == 0:
        return {}
    share = None if spec.noise_size is None else -(-spec.noise_size // len(spec.noise))
    chosen: dict[str, str] = {}
    for kind in spec.noise:
        candidates = [r for r in rows if kind.cond.test(r) and r.id not in needed and r.id not in chosen]
        for row in spread(candidates, share):
            if spec.noise_size is not None and len(chosen) >= spec.noise_size:
                break
            chosen[row.id] = kind.reason
    return dict(sorted(chosen.items()))


def load_chat_specs(company: str, ctx: Context) -> list[ChatSpec]:
    """Import `scripts/dataset/chat_bank_<company>.py` and ask it for the company's specs (it may reuse retrieval questions)."""
    retrieval = {(s.id, s.version): s for s in load_specs(company, ctx)}
    module = importlib.import_module(f"scripts.dataset.chat_bank_{company}")
    return cast(list[ChatSpec], module.specs(ctx, retrieval))


def compute_records(company_dir: Path, specs: list[ChatSpec], ctx: Context) -> list[ChatRecord]:
    """Compute the file record of every spec: what it needs and its noise, over every commitment of the dataset."""
    rows = load_rows(company_dir, ctx)
    ids = [(s.id, s.version) for s in specs]
    if len(set(ids)) != len(ids):
        raise ValueError("two specs share an id and a version")
    for spec in specs:
        reasons = [n.reason for n in spec.noise]
        if len(set(reasons)) != len(reasons):
            raise ValueError(f"{spec.id}: two kinds of noise share a reason, so the file could not tell them apart")
    return [
        {
            "id": spec.id,
            "version": spec.version,
            "category": spec.category,
            "question": spec.question,
            "rule": spec.needed.text,
            "noise_rules": {n.reason: n.cond.text for n in spec.noise},
            "needed": sorted(r.id for r in rows if spec.needed.test(r)),
            "noise": pick_noise(spec, rows),
        }
        for spec in specs
    ]


def compare(computed: list[ChatRecord], published: list[ChatRecord]) -> list[str]:
    """List the differences between the computed records and the published file."""
    problems = []
    by_key = {(r["id"], r["version"]): cast(dict[str, object], r) for r in computed}
    for old in cast(list[dict[str, object]], published):
        key = (str(old["id"]), str(old["version"]))
        if key not in by_key:
            problems.append(f"{key[0]} {key[1]}: published but missing from the spec (a published question is never removed)")
        elif by_key[key] != old:
            changed = [f for f in old if by_key[key].get(f) != old[f]]
            problems.append(f"{key[0]} {key[1]}: differs from the file in {', '.join(changed)} (use a new version)")
    return problems


def build_bank(company_dir: Path) -> list[ChatRecord]:
    """Compute the bank of a company from its spec and its `expected` files."""
    ctx = load_context(company_dir)
    return compute_records(company_dir, load_chat_specs(company_dir.name, ctx), ctx)


def check_company_chat_bank(company_dir: Path) -> list[str]:
    """Return the problems of the company's chat bank file (none if it is consistent); used by check_dataset.py."""
    path = company_dir / BANK_FILE
    if not path.exists():
        return []
    try:
        return compare(build_bank(company_dir), read_bank(path))
    except ModuleNotFoundError:
        return [f"{BANK_FILE} exists but scripts/dataset/chat_bank_{company_dir.name}.py does not"]
    except (KeyError, ValueError, OSError) as error:
        return [f"{BANK_FILE} cannot be computed: {type(error).__name__}: {error}"]


def print_summary(records: list[ChatRecord]) -> None:
    """Print the size of the bank per category: questions, what they need and how much noise they bring."""
    by_category: dict[str, list[ChatRecord]] = defaultdict(list)
    for r in records:
        by_category[r["category"]].append(r)
    print(f"{'category':<14}{'questions':>10}{'needed min':>11}{'median':>7}{'max':>5}{'noise median':>13}{'max':>5}")
    for category, items in by_category.items():
        needed = [len(r["needed"]) for r in items]
        noise = [len(r["noise"]) for r in items]
        print(
            f"{category:<14}{len(items):>10}{min(needed):>11}{int(statistics.median(needed)):>7}{max(needed):>5}"
            f"{int(statistics.median(noise)):>13}{max(noise):>5}"
        )
    print(f"{'total':<14}{len(records):>10}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company")
    parser.add_argument("--check", action="store_true", help="verify the file, do not write it")
    args = parser.parse_args(argv)

    company_dir = DATA_DIR / args.company
    if not (company_dir / "company.json").exists():
        print(f"no dataset at {company_dir}")
        return 1
    try:
        ctx = load_context(company_dir)
        computed = compute_records(company_dir, load_chat_specs(args.company, ctx), ctx)
    except ModuleNotFoundError:
        print(f"scripts/dataset/chat_bank_{args.company}.py does not exist: write it with a specs(ctx, retrieval) function first")
        return 1
    except (KeyError, ValueError, OSError) as error:
        print(f"cannot build the bank: {type(error).__name__}: {error}")
        return 1
    path = company_dir / BANK_FILE
    published = read_bank(path)

    problems = compare(computed, published)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    if not args.check:
        added = len(computed) - len(published)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in computed), encoding="utf-8")
        print(f"{BANK_FILE}: {len(computed)} questions ({added} added)\n")
    print_summary(computed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
