"""Step 1: zero-shot baseline. One LLM call -> run code once -> check facts. No retries, no reflection.

Run:  python step1_baseline.py            (5 runs)
      python step1_baseline.py --runs 10
"""
import argparse
import re
import pandas as pd

import config
from src.checker import check, extract_results, score, strict_json_ok, report_precision
from src.llm import chat
from src.runner import run_code
from src.trace import Run
from src.schema import data_schema

PROMPT = (config.ROOT / "prompts" / "step1_baseline.txt").read_text(encoding="utf-8")
PROMPT = PROMPT.replace("<<SCHEMA>>", data_schema())

def data_schema(n_rows=3):
    """Spaltennamen, dtypes und ein paar Beispielzeilen fuer den Prompt."""
    df = pd.read_csv(config.DATA_DIR / config.DATA_FILE, low_memory=False, nrows=1000)
    cols = "\n".join(f"- {c} ({t})" for c, t in df.dtypes.astype(str).items())
    sample = df.drop(columns=["cpd_filename"]).head(n_rows).to_csv(index=False)
    return f"\nColumns (name and dtype):\n{cols}\n\nFirst {n_rows} rows (CSV):\n{sample}"

def extract_code(text):
    """Take the first ```python block; fall back to any ``` block; else None"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```python\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1)
    return None

def one_run(i, use_schema=False):
    cfg = "step1_schema" if use_schema else "step1_baseline"
    prompt = PROMPT.replace("{SCHEMA}", data_schema() if use_schema else "")
    run = Run(cfg)
    try:
        answer = chat(run, [{"role": "user", "content": prompt}], label="generate")
    except Exception as e:
        # LLM-Call gescheitert (Timeout, Verbindung weg, ...): im Trace festhalten und weiter
        run.log("error", label="generate", error_type=type(e).__name__, error=str(e))
        summary = {
            "config": cfg,
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
        "config": cfg,
        "code_found": code is not None,
        "exit_code": res["exit_code"],
        "results_json_found": results is not None,
        "results_json_strict": strict_json_ok(res["stdout"]),
        "report_precision": report_precision(res["stdout"]),
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
    ap.add_argument("--schema", action="store_true", help="Spalten + Beispielzeilen in den Prompt")
    args = ap.parse_args()
    for i in range(1, args.runs + 1):
        one_run(i, use_schema=args.schema)
    print("\nNext: python analyze_runs.py   (and READ the traces in runs/)")