"""Step 1: zero-shot baseline as an experiment. Per seed: generate v1 -> execute -> evaluate.

v1 of every seed is frozen here; the reflection levels (2a, 2b, 2c) later start from exactly these v1s.

Run:  python step1_baseline.py --exp E01_baseline_schema --schema --seeds 101-105
      python step1_baseline.py --exp E01_baseline_blind --seeds 101-105
      (same command again = resume: seeds that already have a result are skipped)
"""
import argparse
import re

import config
from src.evaluate import evaluate_version, summary_line
from src.experiment import Experiment, parse_seeds
from src.llm import chat
from src.runner import run_code
from src.schema import data_schema
from src.trace import Case

PROMPT = (config.ROOT / "prompts" / "step1_baseline.txt").read_text(encoding="utf-8")


def extract_code(text):
    """Take the first ```python block; else None"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```python\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1)
    return None


def build_prompt(use_schema):
    """The generate prompt, with or without the data schema. Returns (prompt, schema_text)."""
    schema = data_schema() if use_schema else ""
    return PROMPT.replace("{SCHEMA}", schema), schema


def generate_v1(case, prompt):
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
    res = run_code(v1, code) if code is not None else None
    return evaluate_version(v1, code, res)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, help="experiment id, e.g. E01_baseline_schema")
    ap.add_argument("--schema", action="store_true", help="column names + example values in the prompt")
    ap.add_argument("--seeds", default="101-105", help="e.g. 101-105 or 101,103")
    ap.add_argument("--note", default="", help="free text for the manifest")
    args = ap.parse_args()

    prompt, schema = build_prompt(args.schema)
    prompts = {"generate": PROMPT, **({"schema": schema} if schema else {})}
    exp = Experiment(args.exp, "baseline", prompts, parse_seeds(args.seeds),
                     data_context="schema" if args.schema else "blind", note=args.note)

    print(f"Experiment {exp.id}: seeds {exp.seeds}")
    for seed in exp.seeds:
        if exp.is_done(seed, "v1"):
            print(f"s{seed} v1  already done, skipped")
            continue
        print(summary_line(generate_v1(Case(exp, seed), prompt)))
    exp.finish()
    print(f"\nDone: {exp.dir}")
