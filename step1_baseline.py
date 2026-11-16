"""Step 1: zero-shot baseline as an experiment. Per seed: generate v1 -> execute -> evaluate.

v1 of every seed is frozen here; the reflection levels (2a, 2b, 2c) later start from exactly these v1s.

Run:  python step1_baseline.py --exp B4_strong --prompt step1_baseline_v2 --schema --shims --seeds 101-105 --change "..."
      (--prompt is required: a file in prompts/ without .txt, e.g. step1_baseline_v1 (original) or step1_baseline_v2 (+ definition of "strong");
       old-series prompts are in prompts/legacy/, e.g. --prompt legacy/step1_baseline_v3. --shims = run with the SHIM of src/runner.py)
      python step1_baseline.py --exp <new_id> --rerun-from <baseline_id> [--shims] --change "..."
      (--rerun-from: same code again, no LLM call; with or without --shims. Measures the environment alone)
      python step1_baseline.py --exp B1_original_prompt --prompt step1_baseline_v1 --seeds 101-105 --change "..."
      (same command again = resume: seeds that already have a result are skipped)
"""
import argparse
import re

import config
from src.evaluate import evaluate_version, summary_line
from src.experiment import Experiment, change_missing, load, parse_seeds
from src.llm import chat
from src.runner import run_code
from src.schema import data_schema
from src.trace import Case

PROMPT = (config.ROOT / "prompts" / "step1_baseline_v1.txt").read_text(encoding="utf-8")  # the original prompt


def extract_code(text):
    """Take the first ```python block; else None"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```python\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1)
    return None


def load_prompt(name):
    """Text of prompts/<name>.txt (e.g. step1_baseline_v1, or legacy/step1_baseline_v3)."""
    return (config.ROOT / "prompts" / f"{name}.txt").read_text(encoding="utf-8")


def build_prompt(use_schema, template=None):
    """The generate prompt, with or without the data schema. Returns (prompt, schema_text)."""
    schema = data_schema() if use_schema else ""
    return (template or PROMPT).replace("{SCHEMA}", schema), schema


def generate_v1(case, prompt, shims=False, report_helper=False):
    """generate -> execute -> evaluate for one seed. Returns the result of v1."""
    v1 = case.version("v1")
    try:
        answer = chat(v1, [{"role": "user", "content": prompt}], label="generate", seed=case.seed)
    except Exception as e:
        # LLM call failed (timeout, connection lost, ...): record it and go on with the next seed
        v1.log("error", stage="generate", error_type=type(e).__name__, error=str(e))
        return evaluate_version(v1, None, llm_error=type(e).__name__)

    v1.save("response.md", answer)
    code = extract_code(answer)
    res = run_code(v1, code, shims=shims, report_helper=report_helper) if code is not None else None
    return evaluate_version(v1, code, res)


def rerun_v1(case, base_id, shims):
    """No LLM call: run the frozen v1 code of a base experiment again (with or without shims) and evaluate it.
    The code is the same, so a difference to the base is caused by the environment alone. None if the base has no code."""
    code_file = config.EXPERIMENTS_DIR / base_id / "cases" / f"s{case.seed}" / "v1" / "code.py"
    if not code_file.exists():
        return None
    code = code_file.read_text(encoding="utf-8")
    ver = case.version("rerun", parent=f"{base_id}/s{case.seed}/v1")
    return evaluate_version(ver, code, run_code(ver, code, shims=shims))


def main_rerun(args):
    base = load(args.rerun_from)
    if base["level"] != "baseline":
        raise SystemExit(f"--rerun-from must be a baseline experiment, '{args.rerun_from}' has level {base['level']}")
    seeds = parse_seeds(args.seeds) if args.seeds else base["seeds"]
    exp = Experiment(args.exp, "rerun", {}, seeds, base=args.rerun_from, data_context=base["data_context"],
                     runner_shims=args.shims, change=args.change, note=args.note)
    print(f"Experiment {exp.id}: v1 code of {args.rerun_from} again, shims {'ON' if args.shims else 'off'}, seeds {exp.seeds}")
    for seed in exp.seeds:
        if exp.is_done(seed, "rerun"):
            print(f"s{seed} rerun  already done, skipped")
            continue
        result = rerun_v1(Case(exp, seed), args.rerun_from, args.shims)
        print(summary_line(result) if result else f"s{seed} rerun  skipped: {args.rerun_from} has no code for this seed")
    exp.finish()
    print(f"\nDone: {exp.dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, help="experiment id, e.g. B4_strong")
    ap.add_argument("--schema", action="store_true", help="column names + example values in the prompt")
    ap.add_argument("--seeds", default="101-105", help="e.g. 101-105 or 101,103")
    ap.add_argument("--prompt", required=True, help="prompt file in prompts/ (without .txt), e.g. step1_baseline_v1")
    ap.add_argument("--shims", action="store_true", help="run the code with SHIM loaded (display, numpy-safe json)")
    ap.add_argument("--report-helper", action="store_true",
                    help="run the code with report(key, value) available (writes /outputs/results.json); use with the current prompt")
    ap.add_argument("--change", default="", help="what is different from the experiment you compare with (required for a new experiment)")
    ap.add_argument("--rerun-from", help="no LLM call: run the v1 code of this baseline experiment again "
                                         "(with --shims or without); the new experiment has level 'rerun'")
    ap.add_argument("--note", default="", help="free text for the manifest")
    args = ap.parse_args()
    if change_missing(args.exp, args.change):
        ap.error("--change is required for a new experiment: one sentence on what is different from the one you compare with")

    if args.rerun_from:
        main_rerun(args)
        raise SystemExit(0)

    template = load_prompt(args.prompt)
    prompt, schema = build_prompt(args.schema, template)
    prompts = {"generate": template, **({"schema": schema} if schema else {})}
    exp = Experiment(args.exp, "baseline", prompts, parse_seeds(args.seeds),
                     data_context="schema" if args.schema else "blind", runner_shims=args.shims,
                     report_helper=args.report_helper, change=args.change, note=args.note)

    print(f"Experiment {exp.id}: seeds {exp.seeds}")
    for seed in exp.seeds:
        if exp.is_done(seed, "v1"):
            print(f"s{seed} v1  already done, skipped")
            continue
        print(summary_line(generate_v1(Case(exp, seed), prompt, shims=args.shims, report_helper=args.report_helper)))
    exp.finish()
    print(f"\nDone: {exp.dir}")
