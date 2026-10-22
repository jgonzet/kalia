# Measurements

Log of how long the app takes with a real LLM and how much the model writes, on the machine where it was measured. These numbers
depend on the hardware and the model, so they are kept here with both. How good the answers are is measured apart, by the
`scripts/evaluate_*.py` scripts, and logged in `runs/metrics.jsonl` (see the README).

## How to add an entry

1. `uv run scripts/measure_latency.py` (`--help` lists the options). It prints the report in the format below; the LLM it measures is the
   answerer's, so set `ANSWERER_LLM_*` or `LLM_*` first.
2. Paste the report at the end of this file and fill in **Observations**: what the numbers say, what surprised you, what stays open.
3. Entries go in order, newest at the bottom, and are not rewritten. When something an entry left open is resolved, add a dated
   "Resolved YYYY-MM-DD: ..." line under it.

Two entries can be compared only if they have the same question fingerprint (it covers the ids, versions, texts and order of the
questions) and a similar machine. A measurement made another way (by hand, with a script that is not kept) says so under **Method**.

To report your own numbers, open an issue with the report the script printed.

## Format of an entry

```
### YYYY-MM-DD — <title>

**Commit:** <short hash> (with uncommitted changes, if so)

**Machine**: GPU, CPU, RAM, power (charger connected or on battery), OS
**Configuration**: backend, model, context window, timeout
**Method**: the command, the questions (how many, where from, fingerprint), warm-up
**Results**: seconds per answer and tokens written (median, p90, max), writing speed, answers degraded, answers over 60 s / 120 s /
the timeout, the GPU while measuring, the slowest five
**Observations**: free text
```

## Entries

The entries of 2026-10-21 were taken before the changes of #38 were committed, so their commit is the one before them and says
"with uncommitted changes".

### 2026-10-21 — Whole chat bank

**Commit:** e4d2871 (with uncommitted changes)

**Machine**
- GPU: NVIDIA GeForce RTX 4080 Laptop GPU, 595.91.07, 12282 MiB
- CPU: 13th Gen Intel(R) Core(TM) i9-13980HX
- RAM: 31 GiB
- Power: charger connected
- OS: Linux 7.0.0-38-generic

**Configuration** (the answerer's LLM)
- Backend: ollama; model: qwen2.5:14b
- Context window: 10240 tokens; timeout: 120 s per attempt

**Method**
- Command: `uv run scripts/measure_latency.py --title Whole chat bank`
- Questions: 64 from `data/lamanija/chat_bank.jsonl` (latest version of each question), fingerprint `58539401af8f`
- Warm-up before measuring: yes

**Results**

| | median | p90 | max |
|---|---|---|---|
| Seconds per answer | 4.0 | 10.8 | 31.7 |
| Tokens written | 147 | 434 | 1255 |

- Writing speed: median 43.1 tokens/s, minimum 40.8
- Answers that came back degraded: 0 of 64
- Answers over 60 s: 0; over 120 s: 0; over the timeout: 0
- GPU while measuring (185 samples, every 2 s): up to 89 °C and 152 W; thermal slowdown in 23, power cap in 164, power brake in 0 of the samples

Slowest 5:

| Question | seconds | tokens written | commitments given |
|---|---|---|---|
| topic-demo | 31.69 | 1199 | 73 |
| direction-owed-to-me | 31.68 | 1255 | 73 |
| date-overdue | 19.19 | 760 | 73 |
| direction-mine | 13.73 | 496 | 73 |
| combination-received-project | 12.48 | 494 | 73 |

**Observations:** Same questions as the first run of the day, which was taken by hand (see the last entry): there the slowest answer took 71.6 s ("¿Cómo viene todo?", 2786 tokens); here it did not reach the five slowest (the longest took 31.7 s). So the same question and the same prompt gave answers of very different length between runs. The five slowest all had the 73 commitments of the whole list in the prompt; time follows the tokens written (about 43 per second). Nothing degraded, nothing over the timeout.

### 2026-10-21 — The question that brings every commitment, repeated

**Commit:** e4d2871 (with uncommitted changes)

**Machine**
- GPU: NVIDIA GeForce RTX 4080 Laptop GPU, 595.91.07, 12282 MiB
- CPU: 13th Gen Intel(R) Core(TM) i9-13980HX
- RAM: 31 GiB
- Power: charger connected
- OS: Linux 7.0.0-38-generic

**Configuration** (the answerer's LLM)
- Backend: ollama; model: qwen2.5:14b
- Context window: 10240 tokens; timeout: 120 s per attempt

**Method**
- Command: `uv run scripts/measure_latency.py --ask ¿Cómo viene todo? --repeat 12 --title The question that brings every commitment, repeated`
- Questions: 12 from asked with --ask: `¿Cómo viene todo?`, fingerprint `33b9b0f9dd33`
- Warm-up before measuring: yes

**Results**

| | median | p90 | max |
|---|---|---|---|
| Seconds per answer | 36.0 | 61.3 | 63.4 |
| Tokens written | 1403 | 2394 | 2476 |

- Writing speed: median 40.6 tokens/s, minimum 40.2
- Answers that came back degraded: 0 of 12
- Answers over 60 s: 2; over 120 s: 0; over the timeout: 0
- GPU while measuring (228 samples, every 2 s): up to 87 °C and 150 W; thermal slowdown in 227, power cap in 1, power brake in 0 of the samples

Slowest 5:

| Question | seconds | tokens written | commitments given |
|---|---|---|---|
| ask-1 | 63.36 | 2476 | 73 |
| ask-1 | 61.32 | 2394 | 73 |
| ask-1 | 51.89 | 2036 | 73 |
| ask-1 | 44.94 | 1768 | 73 |
| ask-1 | 43.35 | 1707 | 73 |

**Observations:** The question that brings all 73 commitments wrote from short to 2476 tokens in the same conditions. Two of 12 answers took more than 60 s, so a 60 s timeout would have degraded them; the longest took 63.4 s. A run of the same 12 questions taken by hand the same day gave 4 of 12 over 60 s and a longest of 70.2 s (510 to 2726 tokens), so in the 24 answers of both: 6 over 60 s, none over 120 s. The GPU was in thermal slowdown in 227 of 228 samples (up to 87 °C) and the model wrote at 40.6 tokens/s instead of about 43: about 6 % slower. What makes this question slow is how much the model writes, not the speed.

### 2026-10-21 — A question with 15 commitments, repeated

**Commit:** e4d2871 (with uncommitted changes)

**Machine**
- GPU: NVIDIA GeForce RTX 4080 Laptop GPU, 595.91.07, 12282 MiB
- CPU: 13th Gen Intel(R) Core(TM) i9-13980HX
- RAM: 31 GiB
- Power: charger connected
- OS: Linux 7.0.0-38-generic

**Configuration** (the answerer's LLM)
- Backend: ollama; model: qwen2.5:14b
- Context window: 10240 tokens; timeout: 120 s per attempt

**Method**
- Command: `uv run scripts/measure_latency.py --ask ¿Qué compromisos hay esta semana? --repeat 20 --title A question with 15 commitments, repeated`
- Questions: 20 from asked with --ask: `¿Qué compromisos hay esta semana?`, fingerprint `3effd78299cf`
- Warm-up before measuring: yes

**Results**

| | median | p90 | max |
|---|---|---|---|
| Seconds per answer | 9.3 | 9.3 | 10.2 |
| Tokens written | 382 | 382 | 421 |

- Writing speed: median 42.9 tokens/s, minimum 42.8
- Answers that came back degraded: 0 of 20
- Answers over 60 s: 0; over 120 s: 0; over the timeout: 0
- GPU while measuring (88 samples, every 2 s): up to 87 °C and 150 W; thermal slowdown in 82, power cap in 5, power brake in 0 of the samples

Slowest 5:

| Question | seconds | tokens written | commitments given |
|---|---|---|---|
| ask-1 | 10.25 | 421 | 15 |
| ask-1 | 9.33 | 382 | 15 |
| ask-1 | 9.33 | 382 | 15 |
| ask-1 | 9.32 | 382 | 15 |
| ask-1 | 9.32 | 382 | 15 |

**Observations:** A question with 15 commitments in the prompt never took more than 10.3 s in 20 runs and wrote 382 tokens in nearly all of them. It did not reproduce the timeouts of the evening of 2026-10-21 (last entry), which happened with the charger disconnected.

### 2026-10-21 — Cold start: first question after unloading the model

**Commit:** e4d2871 (with uncommitted changes)

**Machine**
- GPU: NVIDIA GeForce RTX 4080 Laptop GPU, 595.91.07, 12282 MiB
- CPU: 13th Gen Intel(R) Core(TM) i9-13980HX
- RAM: 31 GiB
- Power: charger connected
- OS: Linux 7.0.0-38-generic

**Configuration** (the answerer's LLM)
- Backend: ollama; model: qwen2.5:14b
- Context window: 10240 tokens; timeout: 120 s per attempt

**Method**
- Command: `uv run scripts/measure_latency.py --cold --ask ¿Qué compromisos hay esta semana? --title Cold start: first question after unloading the model`
- Questions: 1 from asked with --ask: `¿Qué compromisos hay esta semana?`, fingerprint `e9d382c205c7`
- Warm-up before measuring: no (cold start)

**Results**

| | median | p90 | max |
|---|---|---|---|
| Seconds per answer | 11.5 | 11.5 | 11.5 |
| Tokens written | 379 | 379 | 379 |

- Writing speed: median 43.4 tokens/s, minimum 43.4
- Answers that came back degraded: 0 of 1
- Answers over 60 s: 0; over 120 s: 0; over the timeout: 0
- GPU while measuring (6 samples, every 2 s): up to 66 °C and 150 W; thermal slowdown in 0, power cap in 5, power brake in 0 of the samples

Slowest 5:

| Question | seconds | tokens written | commitments given |
|---|---|---|---|
| ask-1 | 11.5 | 379 | 15 |

**Observations:** The first question after unloading the model took 11.5 s, against about 9 s for the same question warm (entry "A question with 15 commitments, repeated"). Loading the model takes about 2 s on this machine (measured by hand: 1.9 s).

### 2026-10-21 — Measurements taken by hand before `measure_latency.py` existed

**Commit:** e4d2871 (with uncommitted changes)

**Machine and configuration:** the same as the entries above (charger connected unless said otherwise), except the timeout, which was 60 s until the middle of the evening and 120 s after.

**Method:** scripts kept in a temporary directory, not in the repository. The runs of 1 and 2 are the same as `measure_latency.py` with the same questions; 3 and 4 have no equivalent in the script.

**1. The chat bank, first run** (64 questions through `POST /chat`, no limits): tokens written median 162, p90 487, max 2786; seconds median 4.4, p90 12.3, max 71.6 (one answer over 60 s, "¿Cómo viene todo?"); writing speed median 42.9 tokens/s, minimum 40.0; none degraded.

**2. "¿Qué compromisos hay esta semana?" 20 times, and "¿Cómo viene todo?" 12 times:** the first wrote 186 to 382 tokens (max 9.3 s); the second 510 to 2726 tokens (13 to 70 s), 4 of 12 over 60 s, with the GPU at 86 °C, thermal slowdown in 158 of 223 samples, clock 1950 to 2310 MHz (maximum 3105) and 40.1 to 41.1 tokens/s.

**3. Asking for a length in the prompt.** The prompt of the app plus the line `Límite de longitud: respondé en 10 líneas como máximo.` at the end (the file was not kept; the repository's prompt was not touched). Two runs of `evaluate_chat.py lamanija --no-log` with each prompt, commitments the answers said of the 564 needed:

| | run 1 | run 2 |
|---|---|---|
| Prompt of the app | 365 (199 missing, 40 extra, 4 invented) | 397 (167 missing, 44 extra, 4 invented) |
| With the limit | 287 (277 missing, 36 extra, 0 invented) | 262 (302 missing, 31 extra, 0 invented) |

Through `POST /chat` (the 64 questions once) the longest answer went from 2786 to 440 tokens, and 16 of 64 answers still had more than 10 lines. "¿Cómo viene todo?" said 41 and 67 of 75 without the limit and 9 and 2 with it. Asking for a length shortens the answers but the model leaves out about 100 more commitments, so the prompt of the app does not carry it.

**4. A cap on the tokens written, simulated on the 64 answers of 1** (how many it would have cut, and the longest wait at 43 tokens/s): 512 tokens, 6 and 12 s; 1024, 3 and 24 s; 2048, 1 and 48 s; 3072, 0 and 71 s; 4096, 0 and 95 s. Not adopted: with the timeout at 120 s it would add little.

**5. Chat requests that did not finish, 19:28 to 19:39** (questions that normally take under 10 s, "esta semana" among them): seven requests between 19:28 and 19:34, six cut by the client's 1-minute timeout and one at 49 s when that run was stopped by hand, and another cut at 2 minutes at 19:38.
- Ollama's log shows a status 500 at exactly the client's timeout for each, no error, no reload of the model.
- The laptop was on battery (discharging until 19:39:37, charging from 19:41), drawing 93 to 113 W during the window against 26 W idle. The kernel logged ACPI events ("acpi_os_execute_deferred hogged CPU") at 19:27, 19:27, 19:28 and 19:32. Everything was fast again when the charger was connected.
- The speed does not explain it: with the GPU in thermal slowdown the model still wrote at 40 to 41 tokens/s (entry above). Counters of the GPU since the driver was loaded (the boot, at 12:11), read at 20:29: thermal slowdown 2753 s, power cap 3291 s, hardware power brake 115 s.
- The code is not the cause: the commit before these changes behaved the same, but two runs overlapped when that was tried, so it proves little.
- Not reproduced in the more than 250 answers taken with the charger connected.

**Observations:** The cause of those requests not finishing is open. The hypothesis the timeline supports is the battery (a limit on the power the laptop gives the GPU); it is confirmed or discarded by repeating `uv run scripts/measure_latency.py --ask "¿Qué compromisos hay esta semana?" --repeat 20` with the charger disconnected and adding the report here.
