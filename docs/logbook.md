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

## 2026-10-09 – Experiment structure for Step 2 (Mischa)

### 9. Problem
Runs were collected flat in `runs/`; the folder name (`…_step1_schema_…`) was the only record of the
conditions. Prompt version, schema version, temperature and code version were not stored, so runs from
different conditions silently ended up in the same group (entry 7 had to filter by date by hand). Within a
2a run, v1 and the revised code were only `step_002.py` / `step_004.py`, and v1 was never executed, so a
revision could not be compared with its own starting point.

### 10. Design: experiment → case → version
- **Experiment** = one set of fixed conditions, folder `experiments/<id>/` with a manifest
  (`experiment.json`): level, base, model + digest, temperature, max_tokens, prompt hashes (+ copies),
  git commit/dirty, machine, status. Resuming an id with different conditions is refused.
- **Case** = one seed inside an experiment (`cases/s101/`), with one `trace.jsonl`.
- **Version** = one code version of a case (`v1`, `2a`, `2b`, `2c`), each with its own folder:
  `response.md`, `code.py`, `stdout.txt`, `stderr.txt`, `outputs/`, `result.json`
  (+ `feedback.md`, `critique.md` for reflection). Every trace line carries `version` and `stage`.
- **Reflection levels branch from the same frozen v1**:

  ```
  case s101
    v1  generate                   = baseline     (executed, frozen; experiment E01)
     ├─ 2a   parent=v1  info: code                                    (E02)
     ├─ 2b   parent=v1  info: code + artifacts                        (E03)
     └─ 2c   parent=v1  info: code + artifacts + checker facts        (E04)
  ```

- **Why branches and not a ladder (2b revising the output of 2a):** the task escalates the *information*
  the critic gets, not the number of revision rounds. In a ladder, an improvement in 2c could not be
  attributed (2a might already have fixed it), errors from one level would carry into the next (entry 7:
  2a swaps errors), and 2c would have had three revision rounds against one for 2a. With branches every
  level does exactly one critique + revise from the same v1; the information is the only variable.
  A ladder can still be run later as a separate experiment (`parent` can point to any version).

### 11. Seed test: the seed does not reproduce long answers
Seed 101 was generated twice in two experiments (T01, T02, same prompt, schema, model, T=0.7):

| | T01 | T02 |
|---|---|---|
| definition of "strong" | `GOES_flux_time_of_flare >= 1e-6` | `goes_estimated_mean_flux >= 6e-7` |
| result | crash `json_serialize`, 2 plots | crash `ValueError` ('M' frequency), 0 plots |

Short answers (40 tokens) are identical for the same seed and differ for another seed, streamed or not,
so Ollama does use the seed. Long answers (~1,500 tokens) drift apart after a few hundred tokens,
probably from small numeric differences on the CPU (e.g. a cached prompt on the second call).
- **Decision:** comparability comes from the **frozen v1**, not from the seed. Reflection levels load v1
  from the base experiment and never regenerate it. The seed names the case across all experiments.
- For the report: "seeded, but not bit-for-bit reproducible for long outputs".

### 12. What the critic sees per level (`src/feedback.py`)
| Level | In addition to its own code |
|---|---|
| 2a | nothing |
| 2b | exit code, stdout (head + tail), last 25 lines of the traceback, a text description of every plot |
| 2c | 2b + independent check of each RESULTS_JSON value: supported / refuted / missing |

- The feedback is put in front of the **same** critique prompt for every level; the revise prompt is the same
  too. Only the information differs.
- Plots: qwen3 cannot read images, so each PNG is described in text (size, "appears empty" or the share of
  the area that is drawn). A vision model is an option for later (`judge_plots()`).
- 2c reports only whether a claim holds, **never the correct value**; otherwise 2c would measure copying the
  answer instead of reflection. The check uses the same checker as the evaluation; this is the "dedicated
  code snippet" of the task.
- In 2b/2c the critic sees the run of v1. v1 is now always executed; 2a still does not see the result.

### 13. Evaluation and analysis
- `src/evaluate.py`: one evaluation for every step (before: a copied block in step1 and step2).
  `result.json` per version: exit code, error type/line/category, checker facts, report precision, plots,
  cost (LLM calls, tokens, seconds; an interrupted attempt is not counted twice).
- Error categories were derived from the final error lines of all 48 executions in the old runs
  (`ERROR_RULES`): `hallucinated_column` 16, `date_parse` 8, ok 6, `json_serialize` 5, `period_type` 4,
  `api_misuse` 2, `datetime_type` 2, `infra_docker` 2, `format_error`, `plot_error`, `internal_keyerror` 1 each.
  A first rule counted `df['date'] = pd.to_datetime(df['date'])` as "column created by the code" and put
  7 invented columns into `internal_keyerror`; fixed (an assignment only creates a column if its right side
  does not read it).
  `infra_docker`, `llm_timeout`, `llm_error` are not the model's fault and are excluded from transitions.
  Limitation: the category is a heuristic on the last error line; it says where the code failed, not always why.
- `analyze.py`: `results/versions.csv` (one row per version) and `results/comparison_<base>.html`
  (seed × level, coloured by exit and facts). Transitions of a level vs. v1 of the same seed:
  fixed / broken / swapped / same_error / still_ok.
- `src/llm.py`: the time limit now runs in its own thread and also fires when Ollama sends nothing at all
  (before, the check ran only when a token arrived: runs of 1,962 s with a 600 s limit). The seed is logged.

### 14. Old runs
`tools/migrate_runs.py` sorts `runs/` into `experiments/_legacy/` by (config, hash of the prompt the model
received); `runs/` stays unchanged. Temperature, git commit and seed were not logged then.

| group | runs | note |
|---|---|---|
| L00_invalid | 11 | LLM timeout 6, LLM/config error 5 |
| L01–L04, L07 step1_baseline | 20 | four different prompts; 0 runs finish |
| L05 step1_schema_893e3d | 5 | Jan's schema (2026-10-04); 0 finish |
| L06 step1_schema_47bfcf | 5 | prompt with the "counted by start_UTC" hint; **2 finish**, 11 % facts |
| L08 step1_schema_e804c4 | 8 | baseline of entry 7; 0 finish |
| L09 step2a_reflection_schema_e804c4 | 5 | old 2a; v1 was not executed, so no pairing possible |

### 15. Open
- Run the new baseline and the three levels: E01 (`--schema`, seeds 101–105), then E02 (2a), E03 (2b), E04 (2c).
- Decide whether `results/` goes into the repo (generated; proposal: `.gitignore`).
- `analyze_runs.py` / `evaluate_reports.py` still read only `runs/`; port `report_eval` flags to experiments
  or retire them after the migration.

## Baseline v2, runner helpers, consolidation

### 16. Decisions
- **Baseline v2 = new prompt + runner shims, measured separately.** The prompt (`prompts/step1_baseline_v2.txt`) asks for a
  notebook in `# %%` format and allows scipy; it does not list the sections (data quality, test, conclusion) and does not
  define "strong": the model has to find and decide these itself, as the large reference model did.
- **Runner shims** (`SHIM` in `src/runner.py`): `display` exists, `json.dumps` accepts numpy/pandas values (also as keys). They hide two
  model errors, so they are a recorded condition (manifest `runner_shims`, `shim_hash`).
- **The effects are measured separately:** `step1_baseline.py --rerun-from` runs the code of an existing baseline again with or
  without shims, without an LLM call, so a difference is caused by the environment alone (2x2: old/new prompt x shims off/on).
- **Reflection** runs on the frozen v1 of one baseline; the shims are inherited from that baseline.

### 17. Consolidation (build on Mischa's structure, keep everything that is needed)
Rule: `src/evaluate.py` and `analyze.py` (Mischa) are the base; unique logic of the other files moved into them, only duplicates
were dropped. Verified on the old data before the old files were removed:
- `report_eval.py` (Jan) -> `src/evaluate.py` (`report_quality`): execution, completeness, correctness, method, plots, flags,
  weighted overall. What `evaluate.py` already had (exit code, JSON found/strict, fact score, error category) is read, not computed twice.
  Re-scoring the 40 old runs of `evaluation_summary.csv` gives **identical** execution, completeness, correctness and plots scores;
  `method` differs on purpose: the GOES column check has weight 0 (hint only), because both definitions of "strong" are allowed.
- Report precision: one function (`checker.report_precision`) with Jan's filter (numbers <= 12 are no claims). On real outputs the old
  version counted "3 months" as a correct number (0.667 where the only real number was wrong).
- `analyze_runs.py` (Mischa, Vanessa) -> `analyze.py`: per-fact accuracy, median/min/max, truncated, plots, precision, exec time, LLM calls
  (`PERFORMANCE_LOG.md` sections 4-5). The 42 old runs with a result are identical in `experiments/_legacy` (exit code, facts, plots, JSON,
  tokens, seconds), so `runs/` stays as data and the script is no longer needed.
- `evaluate_reports.py` (Jan, Vanessa) -> `analyze.py`: `--judge`, `--judge-code`, `--human-template`, `--agreement` on versions of an experiment.
  `evaluation_summary.csv` stays as the history of the old scoring.
- `reexecute.py` -> `step1_baseline.py --rerun-from`; `src/notebook.py` -> `src/evaluate.py`; `trace_view.py` -> `analyze.py --trace`;
  `HOWTO.md` -> README; the tests of `test_report_eval.py` and `test_notebook.py` -> `tests/test_evaluate.py`.
- The runner helpers are a text constant (`SHIM`) in `src/runner.py`: no extra file, hash in the manifest.

### 18. Working rule
Never change `src/` while an experiment is running: a running process re-reads files such as the shim at every call.
The consolidation of entry 17 is applied: `report_eval.py`, `analyze_runs.py`, `evaluate_reports.py`, `reexecute.py`,
`src/notebook.py` and their tests are merged into `src/evaluate.py`, `analyze.py`, `step1_baseline.py` and `tests/test_evaluate.py`;
`evaluate_reports.py --run / --details` became `analyze.py --run / --details`.

### 19. Measurement gap: facts read from the report text
- Problem: all facts were measured through the `RESULTS_JSON` line. A script that runs but does not print it scores 0 %,
  although its text may be right or wrong; the metric was blind there.
- Decision (way 1): `text_facts()` in `src/evaluate.py` reads what the prose says (months, busiest month and its count, number of
  strong flares, trend) and compares it with the ground truth. `flares_per_year` and `pct_strong_per_year` are not readable from prose.
  It is an additional measure (`text_fact_score`, `PERFORMANCE_LOG.md` section 4b); `fact_score`, the funnel and the five report
  dimensions are unchanged (the three test cases give the same scores as before).
- A repair of the missing line (a second model call that reminds the model of the format) is not part of the baseline; it belongs to
  the reflection levels.
