"""Step 2a: reflection alone. generate -> critique -> revise -> run the revised code once -> check facts.

The model only sees its own code, never a run result (that is level 2b). Version 1 of the code is
therefore NOT executed; it is kept as a file and in the trace for comparison.

Run:  python step2_reflection.py --runs 1 --schema
      python step2_reflection.py --runs 5 --schema
"""
import argparse

import config
from src.checker import check, extract_results, score, strict_json_ok, report_precision
from src.llm import chat
from src.runner import run_code
from src.schema import data_schema
from src.trace import Run
from step1_baseline import PROMPT, extract_code

CRITIQUE = (config.ROOT / "prompts" / "step2a_critique.txt").read_text(encoding="utf-8")
REVISE = (config.ROOT / "prompts" / "step2a_revise.txt").read_text(encoding="utf-8")


def one_run(i, use_schema=False):
    cfg = "step2a_reflection_schema" if use_schema else "step2a_reflection"
    prompt = PROMPT.replace("{SCHEMA}", data_schema() if use_schema else "")
    run = Run(cfg)
    try:
        messages = [{"role": "user", "content": prompt}]
        v1 = chat(run, messages, label="generate")
        code_v1 = extract_code(v1)
        if code_v1:
            run.save_code(code_v1)                       # kept as a file, but not executed

        messages += [{"role": "assistant", "content": v1}, {"role": "user", "content": CRITIQUE}]
        critique = chat(run, messages, label="critique")

        messages += [{"role": "assistant", "content": critique}, {"role": "user", "content": REVISE}]
        v2 = chat(run, messages, label="revise")
    except Exception as e:
        # LLM call failed (timeout, connection lost, ...): record it in the trace and go on
        run.log("error", label="reflection", error_type=type(e).__name__, error=str(e))
        summary = {"config": cfg, "llm_error": type(e).__name__, "code_found": False, "exit_code": None,
                   "results_json_found": False, "checks": check(None), "fact_score": 0.0, "n_plots": 0}
        run.log("result", **summary)
        print(f"[{i}] {run.run_id}  LLM-Fehler: {type(e).__name__}: {e}")
        return summary

    code = extract_code(v2)
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
    ap.add_argument("--schema", action="store_true", help="columns + example values in the prompt")
    args = ap.parse_args()
    for i in range(1, args.runs + 1):
        one_run(i, use_schema=args.schema)
    print("\nNext: python analyze_runs.py   (and READ the traces in runs/)")
