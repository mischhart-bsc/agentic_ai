# Logbook

## 2026-10-04 – Step 1: Zero-shot baseline
D-x: Data context. All configurations get the same neutral schema (column names, dtypes, 3 sample rows, generated automatically), without the trap notes. Rationale: a blind prompt tests only guessing column names (observed in run …_b5c4: wrong time column, silent "all strong" fallback, hard-coded findings → 0%) and would confound the later comparisons (information vs. mechanism). The blind variant is documented only as the lower bound (1a).

### 1. Hidden thinking in qwen3:4b
solved by Mischa using `qwen3:4b-instruct`

### 2. First baseline
- **Failures:** Column names guessed (`date`, `class`)

### 3. Changes to pipeline and prompt
- Prompt: time range "up to and including February 2026", definition of
  `strong_share_increasing` (full years 2022–2025), RESULTS_JSON as single-line JSON
  with plain Python types.
- New variant `--schema`: column names, dtypes and 3 sample rows in the prompt.
- More tolerant checker: multi-line JSON, Python dict output and numpy types are parsed;
  separate metric `results_json_strict` for correct formatting.
- New metrics: `report_precision` (numbers in the text vs. ground truth),
  `finish_reason` / `truncated` (cut-off answers).
- Sampling as recommended by Qwen: T=0.7, top_p=0.8, top_k=20.

### 4. Baseline (T=0.7, 5 runs each)

| Metric                         | blind        | schema       |
|--------------------------------|--------------|--------------|
| exit code 0                    | 0/5          | 0/5          |
| fact score                     | 0 %          | 0 %          |
| correct time column            | 0/5          | 5/5          |
| wrong GOES column              | –            | 5/5          |
| GOES class parsed as date      | 1/5          | 3/5          |
| report text hard-coded         | 5/5          | 5/5          |
| repetition loop                | 0/5          | 0/5          |
| mean LLM time / tokens         | 49 s / 1,466 | 46 s / 1,341 |
| report score overall (0–1)     | 0.06 ± 0.02  | 0.11 ± 0.08  |

- **What the bare model can do:** It writes plausible, structured code and, with the
  schema, uses the correct time columns.
- **Where it fails:** It picks the wrong GOES column (trap from Step 0), parses columns
  with "time" in their name as dates, makes pandas/matplotlib errors (Period types,
  invented arguments) and hard-codes the report text before computing anything.
  The text systematically contradicts the data.
- **Decision:** No further prompt tuning. These failures are the benchmark for
  Step 2 (reflection) and Step 3 (tool loop with error feedback).

### 5. Report quality evaluation (evaluation framework)
- **New:** `evaluate_reports.py`, `src/report_eval.py`, `src/judge.py`,
  `tests/test_report_eval.py`.
- **Objective, 5 dimensions (0–1):** correctness 0.35, completeness 0.25,
  execution 0.15, method 0.15, plots 0.10, plus flags per run as failure categories.
- **2×2 matrix:** objective per step = execution, method · objective end-to-end =
  correctness, completeness · subjective = LLM judge (rubric with 5 criteria, scale 1–5),
  prepared but will be used in a later step.

## 2026-10-07 – Step 2a: Reflection alone

### 6. Setup
- `step2_reflection.py`: generate -> critique -> revise, revised code is executed once.
  Prompts in `prompts/step2a_critique.txt` and `step2a_revise.txt`.
- The model never sees a run result (that is 2b). Code v1 is kept as a file but not executed.
- The critique prompt is deliberately generic (no hints about columns or types); concrete hints
  would measure hints, not reflection.

### 7. Result (schema mode, 5 baseline runs vs. 5 complete 2a runs, all from 2026-10-07)

| | baseline | 2a |
|---|---|---|
| exit 0 / facts right | 0/5 / 0 % | 0/5 / 0 % |
| LLM calls per run | 1 | 3 |
| tokens per run (prompt + completion) | ca. 2,600 | ca. 12,200 (4.7x) |

- Funnel does not move: every run still fails at "exit 0". One further 2a run ended in a timeout.
- Failures, baseline: `int64 not JSON serializable` 3/5, KeyError 1/5, ValueError 1/5.
  2a: `int64` 1/5, plus KeyError, ValueError, DateParseError, Period-TypeError (5 different crashes).
- The critique is long but generic ("no leap-year handling"); it named none of the actual crash causes
  and not the hard-coded report text. Revising fixed some errors and introduced others.
- Seconds are not comparable with 2026-10-04 (machine was about 4x slower today, even for the
  unchanged generate step); tokens are the reliable cost measure.
- Mixed groups in `analyze_runs.py` (old prompts, 5 runs with AttributeError, timeouts) made
  per-config means unusable; the numbers above filter to 2026-10-07 only.

### 8. Decision
Reflection without feedback only swaps one error for another at 4.7x the tokens.
Most frequent baseline error (`int64` in `json.dumps`) is trivial to fix with an error message,
so it is the test case for 2b (critique + stdout/stderr). Open: bundle runs per experiment
(folder per experiment) so groups stay clean.

### Reflection File Schema
case seed_101
  v1  generate                   = baseline     (executed, frozen)
   ├─ 2a   parent=v1  info: code
   ├─ 2b   parent=v1  info: code + artifacts
   └─ 2c   parent=v1  info: code + artifacts + checker facts
