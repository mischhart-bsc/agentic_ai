"""Step 1: zero-shot baseline. One LLM call -> run code once -> check facts. No retries, no reflection.

Run:  python step1_baseline.py            (5 runs)
      python step1_baseline.py --runs 10
"""
import argparse
import re

import config
from src.checker import check, extract_results, score
from src.llm import chat
from src.runner import run_code
from src.trace import Run

PROMPT = (config.ROOT / "prompts" / "step1_baseline.txt").read_text(encoding="utf-8")

def extract_code(text):
    """Take the first ```python block; fall back to any ``` block; else None"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```python\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1)
    return None

def one_run(i):
    run = Run("step1_baseline")
    try:
        answer = chat(run, [{"role": "user", "content": PROMPT}], label="generate")
    except Exception as e:
        # LLM-Call gescheitert (Timeout, Verbindung weg, ...): im Trace festhalten und weiter
        run.log("error", label="generate", error_type=type(e).__name__, error=str(e))
        summary = {
            "config": "step1_baseline",
            "llm_error": type(e).__name__,
            "code_found": False,
            "exit_code": None,
            "results_json_found": False,
            "checks": check(None),
            "fact_score": 0.0,
            "n_plots": 0,
        }
        run.log("result", **summary)
        print(f"[{i}] {run.run_id}  LLM-Fehler: {type(e).__name__}: {e}")
        return summary

    code = extract_code(answer)
    if code is None:
        res = {"exit_code": None, "stdout": "", "stderr": "no code block found"}
    else:
        res = run_code(run, code)

    results = extract_results(res["stdout"])
    checks = check(results)
    summary = {
        "config": "step1_baseline",
        "code_found": code is not None,
        "exit_code": res["exit_code"],
        "results_json_found": results is not None,
        "checks": checks,
        "fact_score": score(checks),
        "n_plots": len(list((run.dir / "outputs").glob("*.png"))),
    }
    run.log("result", **summary)
    (run.dir / "report.txt").write_text(res["stdout"] or res["stderr"], encoding="utf-8")

    print(f"[{i}] {run.run_id}  exit={res['exit_code']}  json={results is not None}  "
          f"facts={summary['fact_score']:.0%}  plots={summary['n_plots']}")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    n = ap.parse_args().runs
    for i in range(1, n + 1):
        one_run(i)
    print("\nNext: python analyze_runs.py   (and READ the traces in runs/)")