"""Sort the old runs/ (flat, one folder per run) into legacy experiments under experiments/_legacy/.

Runs are grouped by (config, hash of the prompt the model actually received). Runs with a different prompt
were run under different conditions and end up in different groups, even if their config name is the same.
runs/ itself is only read, never changed.

    experiments/_legacy/L03_step1_schema_893e3d/
        experiment.json          status "legacy", source runs, what is unknown (e.g. temperature)
        prompts/generate.txt
        cases/r_<old run id>/
            trace.jsonl          copied unchanged
            v1/ or 2a/           code.py, stdout.txt, stderr.txt, outputs/, result.json (re-evaluated)

Groups:
  runs without a result entry (smoke tests, aborted runs)        -> skipped
  runs whose LLM call failed or where Docker was not running     -> L00_invalid

Run:  python tools/migrate_runs.py            dry run: only print the groups
      python tools/migrate_runs.py --apply    write experiments/_legacy/
"""
import argparse
import hashlib
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from src.evaluate import error_info  # noqa: E402

LEGACY_DIR = config.EXPERIMENTS_DIR / "_legacy"


def read_run(run_dir):
    entries = []
    for line in (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    result = next((e for e in reversed(entries) if e.get("kind") == "result"), None)
    if result is None:
        return None
    llm = [e for e in entries if e.get("kind") == "llm"]
    execs = [e for e in entries if e.get("kind") == "exec"]
    prompt = llm[0]["messages"][0]["content"] if llm and llm[0].get("messages") else ""
    codes = sorted((run_dir / "code").glob("*.py"))
    config_name = result.get("config") or "unknown"
    return {
        "dir": run_dir, "id": run_dir.name, "config": config_name, "result": result, "llm": llm,
        "exec": execs[-1] if execs else None, "prompt": prompt,
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:6],
        "codes": codes, "level": "2a" if config_name.startswith("step2a") else "baseline",
        "data_context": "schema" if "schema" in config_name else "blind",
    }


def is_invalid(run):
    if not run["prompt"] or run["result"].get("llm_error"):
        return True
    ex = run["exec"]
    return ex is not None and error_info(ex.get("stderr"), ex.get("exit_code"), "").get(
        "error_category") == "infra_docker"


def group_runs(runs_dir):
    groups = defaultdict(list)
    skipped = []
    for trace in sorted(list(runs_dir.glob("*/trace.jsonl")) + list(runs_dir.glob("_archive/*/trace.jsonl"))):
        run = read_run(trace.parent)
        if run is None:
            skipped.append(trace.parent.name)
            continue
        key = "invalid" if is_invalid(run) else f"{run['config']}_{run['prompt_hash']}"
        groups[key].append(run)
    # stable names: L00 for invalid, then in order of the first run date
    named = {}
    ordered = sorted((k for k in groups if k != "invalid"), key=lambda k: min(r["id"] for r in groups[k]))
    if "invalid" in groups:
        named["L00_invalid"] = groups["invalid"]
    for i, k in enumerate(ordered, 1):
        named[f"L{i:02d}_{k}"] = groups[k]
    return named, skipped


def migrate_run(run, case_dir):
    """Copy one old run into case_dir and write a result.json in the new format."""
    case_dir.mkdir(parents=True)
    shutil.copy2(run["dir"] / "trace.jsonl", case_dir / "trace.jsonl")
    version = run["level"] if run["level"] == "2a" else "v1"
    vdir = case_dir / version
    (vdir / "outputs").mkdir(parents=True)

    code = run["codes"][-1].read_text(encoding="utf-8") if run["codes"] else None
    if code is not None:
        (vdir / "code.py").write_text(code, encoding="utf-8")
    if version == "2a" and len(run["codes"]) > 1:      # old 2a: v1 was saved but never executed
        (case_dir / "v1").mkdir()
        shutil.copy2(run["codes"][0], case_dir / "v1" / "code.py")
    for png in (run["dir"] / "outputs").glob("*.png"):
        shutil.copy2(png, vdir / "outputs" / png.name)

    ex = run["exec"] or {}
    (vdir / "stdout.txt").write_text(ex.get("stdout") or "", encoding="utf-8")
    (vdir / "stderr.txt").write_text(ex.get("stderr") or "", encoding="utf-8")
    old = run["result"]
    if old.get("llm_error"):
        err = {"error_type": old["llm_error"], "error_category":
               "llm_timeout" if "Timeout" in old["llm_error"] else "llm_error"}
    elif ex:
        err = error_info(ex.get("stderr"), ex.get("exit_code"), code)
    else:
        err = {"error_category": "no_code"}
    llm = run["llm"]
    result = {
        "experiment": None, "seed": None, "version": version,
        "parent": "v1 (not executed)" if version == "2a" else None,
        "llm_error": old.get("llm_error"), "code_found": old.get("code_found"), "exit_code": old.get("exit_code"),
        **{k: err.get(k) for k in ("error_type", "error_category", "error_message", "error_line")},
        **{k: old.get(k) for k in ("results_json_found", "results_json_strict", "report_precision",
                                   "checks", "fact_score", "n_plots")},
        "cost": {"llm_calls": len(llm),
                 "prompt_tokens": sum(e.get("prompt_tokens") or 0 for e in llm),
                 "completion_tokens": sum(e.get("completion_tokens") or 0 for e in llm),
                 "llm_seconds": round(sum(e.get("seconds") or 0 for e in llm), 1),
                 "exec_seconds": round(ex.get("seconds") or 0, 1),
                 "truncated": any(e.get("finish_reason") in ("length", "wall_timeout") for e in llm)},
        "migrated_from": str(run["dir"].relative_to(config.ROOT)),
    }
    return result, vdir


def migrate_group(name, runs):
    exp_dir = LEGACY_DIR / name
    first = runs[0]
    (exp_dir / "prompts").mkdir(parents=True)
    if first["prompt"]:
        (exp_dir / "prompts" / "generate.txt").write_text(first["prompt"], encoding="utf-8")
    for run in runs:
        result, vdir = migrate_run(run, exp_dir / "cases" / f"r_{run['id']}")
        result["experiment"] = name
        (vdir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str),
                                          encoding="utf-8")
    manifest = {
        "id": name, "level": first["level"], "base": None, "status": "legacy",
        "data_context": first["data_context"], "config": first["config"],
        "model": next((e.get("model") for r in runs for e in r["llm"] if e.get("model")), None),
        "temperature": None, "prompts": {"generate": "sha256:" + first["prompt_hash"]} if first["prompt"] else {},
        "seeds": [], "source_runs": [r["id"] for r in runs],
        "note": ("migrated from runs/ by tools/migrate_runs.py; temperature, git commit and seed were not "
                 "logged at that time; old 2a runs never executed v1, so there is no paired v1 result"),
    }
    (exp_dir / "experiment.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write experiments/_legacy/ (default: dry run)")
    args = ap.parse_args()

    groups, skipped = group_runs(config.RUNS_DIR)
    for name, runs in groups.items():
        dates = sorted({r["id"][:8] for r in runs})
        exists = " (exists, skipped)" if (LEGACY_DIR / name).exists() else ""
        print(f"{name:<40} {len(runs):>2} runs  {', '.join(dates)}{exists}")
    print(f"skipped (no result entry): {len(skipped)}")

    if not args.apply:
        print("\nDry run. Write with:  python tools/migrate_runs.py --apply")
        raise SystemExit(0)
    for name, runs in groups.items():
        if not (LEGACY_DIR / name).exists():
            migrate_group(name, runs)
    print(f"\nWritten to {LEGACY_DIR}  (runs/ is unchanged)")
