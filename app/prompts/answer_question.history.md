# History of `answer_question.md`

One row per change of the prompt that was measured: what changed, why, and what it did to the numbers. Git keeps the text of
every version and each run of `scripts/evaluate_chat.py` logs the hash of the prompt it used (`uv run scripts/run_log.py
--stage chat_bank`); this file keeps the reason, which neither of them has. Add a row when a change is measured, before replacing
a prompt that works (see `docs/DECISIONS.md` and the README, "Evaluate the chat").

The first rows were measured with the previous version of the evaluation (the five acceptance questions of `questions.jsonl`
through the real retriever, 140 needed commitments in all, "said" counted with the half-of-the-words heuristic). Those numbers
are not comparable with the ones from the chat bank, which gives the LLM a controlled list and judges people and dates.

| Date | Commit | Prompt | Change and reason | Result |
|---|---|---|---|---|
| 2026-10-16 | 94fc9e5 | first, in English | The first prompt of the chat (#18). | `qwen2.5:14b`: 72 to 81 of about 140 needed commitments in the answers. With `llama3.1` (8B): 46. |
| 2026-10-16 | fee57a4 | in Spanish, state `vencido` | Prompt and states in Spanish, like the data. | 71 and 67. The model read "¿qué vence esta semana?" as a question about what is already overdue. |
| 2026-10-16 | fee57a4 | in Spanish, state `atrasado` | `vencido` renamed `atrasado`, with the rule that "vencidos" means overdue and "vence en un período" means the due date falls in it. | 82 and 85. Temperature 0 changed nothing. |
| 2026-10-16 | 974c3eb | `829f0d32c6c0`, without the ids on the lines | The id and the source document left out of the prompt: the model must not show them and they took about 40% of the tokens of a long list. | 91 and 84 of about 140 (about 62%), with one to four commitments added that were not needed; the retriever brought almost exactly what each question needed, so the rest is the model leaving commitments out. Pasted by hand into Claude (claude.ai) an early version gave 15 of 15 on "my boss" with both directions, and 7 of 14 on "due this week" because of a flaw in that day's wording, corrected since: with a stronger model the design works, and what limits the answers today is the local model. |
| 2026-10-19 | 6e271c1 + uncommitted chat bank | `829f0d32c6c0`, same prompt | First measurement with the chat bank (64 questions, a controlled list, people and dates judged): the baseline to compare the next change with. | `qwen2.5:14b`, four runs: 365, 370, 383 and 384 of 564 needed commitments said (about 66%); 34 to 38 noise commitments said; 5 to 7 lines with a wrong person or direction; no more than one wrong date. Swings come from a few large lists ("¿Cómo viene todo?" 28 to 60 of 75, "¿Qué me deben?" 15 to 28 of 35). Not comparable with the rows above. After these runs the noise of "¿Qué vence este mes?" was changed (overdue ones from earlier months only), so a later run is not identical on that question. |
