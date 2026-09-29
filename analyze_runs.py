"""Aggregates all runs in runs/: reads the 'result' (and 'llm'/'exec') entries of every trace.jsonl
and prints one summary per config (step1_baseline, ...).

Run:  python analyze_runs.py                      (all configs)
      python analyze_runs.py --config step1_baseline
      python analyze_runs.py --details            (additionally one line per run)
"""
import argparse
import json
from collections import defaultdict
from statistics import mean, median

import config


def load_runs():
    """Return a list of dicts, one per run that has a 'result' entry."""
    runs = []
    for trace in sorted(config.RUNS_DIR.glob("*/trace.jsonl")):
        entries = []
        for line in trace.read_text(encoding="utf-8").splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        result = next((e for e in reversed(entries) if e["kind"] == "result"), None)
        if result is None:
            continue  # smoke tests, aborted runs
        llm = [e for e in entries if e["kind"] == "llm"]
        execs = [e for e in entries if e["kind"] == "exec"]
        runs.append({
            "run_id": result["run_id"],
            "result": result,
            "llm_calls": len(llm),
            "llm_seconds": sum(e.get("seconds") or 0 for e in llm),
            "completion_tokens": sum(e.get("completion_tokens") or 0 for e in llm),
            "exec_calls": len(execs),
            "errors": [e for e in entries if e["kind"] == "error"],
        })
    return runs


def pct(part, total):
    return f"{part / total:.0%}" if total else "-"


def summarize(name, runs, details=False):
    n = len(runs)
    res = [r["result"] for r in runs]
    ok_llm = [r for r in runs if not r["result"].get("llm_error")]

    print(f"\n=== {name}  ({n} runs)")
    print(f"  LLM errors          : {n - len(ok_llm)}"
          + (f"  ({', '.join(sorted({r['result']['llm_error'] for r in runs if r['result'].get('llm_error')}))})"
             if len(ok_llm) < n else ""))
    print(f"  code found          : {pct(sum(bool(r.get('code_found')) for r in res), n)}")
    print(f"  exit code 0         : {pct(sum(r.get('exit_code') == 0 for r in res), n)}")
    print(f"  RESULTS_JSON found  : {pct(sum(bool(r.get('results_json_found')) for r in res), n)}")
    print(f"  plots (mean)        : {mean(r.get('n_plots', 0) for r in res):.1f}")

    scores = [r.get("fact_score", 0.0) for r in res]
    print(f"  fact score          : mean {mean(scores):.0%}   median {median(scores):.0%}   "
          f"min {min(scores):.0%}   max {max(scores):.0%}")
    if len(ok_llm) < n and ok_llm:
        print(f"  fact score (w/o LLM errors): mean {mean(r['result'].get('fact_score', 0.0) for r in ok_llm):.0%}")

    # accuracy per fact (None = not in ground truth -> skipped)
    per_fact = defaultdict(list)
    for r in res:
        for k, v in (r.get("checks") or {}).items():
            if v is not None:
                per_fact[k].append(v)
    if per_fact:
        print("  per fact:")
        for k, vals in per_fact.items():
            print(f"    {k:<26} {sum(vals):>3}/{len(vals):<3} {pct(sum(vals), len(vals)):>5}")

    if ok_llm:
        print(f"  LLM time per run    : mean {mean(r['llm_seconds'] for r in ok_llm):.0f}s   "
              f"max {max(r['llm_seconds'] for r in ok_llm):.0f}s")
        print(f"  completion tokens   : mean {mean(r['completion_tokens'] for r in ok_llm):.0f}")
        print(f"  LLM calls per run   : mean {mean(r['llm_calls'] for r in ok_llm):.1f}   "
              f"exec calls per run: mean {mean(r['exec_calls'] for r in ok_llm):.1f}")

    if details:
        print("  runs:")
        for r in runs:
            x = r["result"]
            status = x.get("llm_error") or f"exit={x.get('exit_code')}"
            print(f"    {r['run_id']:<40} {status:<18} json={str(x.get('results_json_found')):<5} "
                  f"facts={x.get('fact_score', 0.0):.0%}  plots={x.get('n_plots', 0)}  "
                  f"llm={r['llm_seconds']:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="only this config, e.g. step1_baseline")
    ap.add_argument("--details", action="store_true", help="one line per run")
    args = ap.parse_args()

    runs = load_runs()
    if args.config:
        runs = [r for r in runs if r["result"].get("config") == args.config]
    if not runs:
        print(f"No finished runs found in {config.RUNS_DIR}")
        raise SystemExit(0)

    groups = defaultdict(list)
    for r in runs:
        groups[r["result"].get("config", "?")].append(r)
    for name, group in sorted(groups.items()):
        summarize(name, group, details=args.details)
