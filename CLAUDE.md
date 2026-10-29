# KALIA

- `docs/VISION.md` is the product direction. Read it before proposing architecture or scope.
- The scope of V0 lives in `docs/SPEC.md`.
- `scripts/` is grouped in `operate/`, `dataset/` and `quality/` since 2026-10-29 (#32). Entries of `docs/PROGRESS.md`, `docs/PROGRESS_ARCHIVE.md` and `docs/DECISIONS.md` written before that date cite scripts by a flat path (`scripts/<name>.py`); file names did not change, so find one with `find scripts -name <name>.py`.

## Synthetic dataset (`data/<company>/`)

The format of every dataset file is defined in `docs/DATASET.md` and the reasons for the choices in `docs/DECISIONS.md`; do not restate either elsewhere.

- Work in this order: `story.md`, then the `expected` files, then the generator prompts, then the documents. Never write a document before its `expected` file exists.
- Before adding documents, extend `story.md` as its header says. Do not contradict a fact already in it; if a fact must change, ask first.
- Never renumber or reuse a document id or a commitment id (`<document id>-cN`): questions and `mentions` point to them. Removing a commitment leaves a gap.
- A commitment is promised in one document only; other documents name it through `mentions`. Following one commitment across documents is issue #4, not dataset work.
- `questions.jsonl`: never edit a published question. New or changed questions get a new `version`.
- The reference date lives only in `company.json`; do not repeat it in other dataset files.
- Editing the text of an accepted document invalidates its `text_sha256`; refresh it. Changing the commitments of an `expected` file after its document was accepted means the text may no longer contain them: re-check the text and the questions that cite those commitments.
- `scripts/dataset/check_dataset.py` checks the documents against their `expected` files. Run it every time you add or edit documents or `expected` files; how and what it checks is in `docs/DATASET.md` ("Checking the dataset").

## Measuring the chat

- To compare a model or a prompt of the chat (`app/prompts/answer_question.md`, `LLM_MODEL`), use `scripts/quality/evals/evaluate_chat.py`; how to run it and how to read its numbers is in the README ("Evaluate the chat"). Do not improvise a one-off harness.
- Before replacing the answering prompt, run the script with `--prompt <new file>` against the current one and repeat the runs: the numbers move between runs of the same prompt (README says by how much).
