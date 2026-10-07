# KALIA

- `docs/VISION.md` is the product direction. Read it before proposing architecture or scope.
- The scope of V0 lives in `docs/SPEC.md`.

## Synthetic dataset (`data/<company>/`)

Formats and the reasons behind them are in `docs/PLAN.md` section 12 and `docs/DECISIONS.md`; do not restate them elsewhere.

- Work in this order: `story.md`, then the `expected` files, then the generator prompts, then the documents. Never write a document before its `expected` file exists.
- Before adding documents, extend `story.md` as its header says. Do not contradict a fact already in it; if a fact must change, ask first.
- Never renumber or reuse a document id or a commitment id (`<document id>-cN`): questions and `mentions` point to them. Removing a commitment leaves a gap.
- A commitment is promised in one document only; other documents name it through `mentions`. Following one commitment across documents is issue #4, not dataset work.
- `questions.jsonl`: never edit a published question. New or changed questions get a new `version`.
- The reference date lives only in `company.json`; do not repeat it elsewhere.
- Editing the text of an accepted document, or its `expected` file, invalidates `text_sha256`; refresh it and re-check the questions that cite its commitments.
