"""Run a whole chain once more as YOUR run: the baseline condition and every reflection condition built on it.

    python tools/run_chain.py B4_strong             continue your last chain, or start your first one
    python tools/run_chain.py B4_strong --new       start a further chain (B4_strong/mischa_2, R1_2a/mischa_2, ...)
    python tools/run_chain.py B4_strong --dry-run   only print the commands

Only existing conditions are repeated: prompt, schema, shims and level come from their condition.json, so a repetition
cannot differ by accident (a new condition is started with step1_baseline.py / step2_reflection.py and --change).
Every reflection run builds on YOUR baseline run of the same chain (paired). The plan is made from what is on disk, so
after an interruption the same command continues where it stopped. Afterwards: python analyze.py
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))   # project folder: config.py, src/

import config  # noqa: E402
from src.experiment import current_person, runs_of  # noqa: E402


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def levels_of(base_cond, root=None):
    """The reflection conditions built on a baseline condition, in level order (2a, 2b, 2c)."""
    root = Path(root or config.EXPERIMENTS_DIR)
    conds = [(d.name, _read(d / "condition.json")) for d in root.iterdir() if (d / "condition.json").exists()]
    return [name for name, c in sorted(conds, key=lambda x: x[1]["level"]) if c.get("base") == base_cond]


def mine(cond, person, root=None):
    """This person's runs of a condition, oldest first: [(run name, run.json)]."""
    root = Path(root or config.EXPERIMENTS_DIR)
    return [(r, _read(root / cond / r / "run.json")) for r in runs_of(cond, root) if r.split("_")[0] == person]


def next_step(base_cond, levels, person, new, root=None):
    """The next command to run (a list of arguments), or None when the chain is complete."""
    base_runs = mine(base_cond, person, root)
    if new or not base_runs:
        return ["step1_baseline.py", "--exp", base_cond, "--repeat"]
    run_name, run = base_runs[-1]
    if run["status"] != "complete":
        return ["step1_baseline.py", "--exp", base_cond]                      # resume the unfinished baseline run
    base_run = f"{base_cond}/{run_name}"
    for cond in levels:
        on_this = [(r, j) for r, j in mine(cond, person, root) if j.get("base_run") == base_run]
        if on_this and on_this[-1][1]["status"] == "complete":
            continue
        cmd = ["step2_reflection.py", "--exp", cond, "--base", base_run]
        return cmd if on_this else cmd + ["--repeat"]                         # resume, or a new run on this base
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("base", help="baseline condition, e.g. B4_strong")
    ap.add_argument("--new", action="store_true", help="start a further chain instead of continuing the last one")
    ap.add_argument("--dry-run", action="store_true", help="only print the next command")
    args = ap.parse_args()

    if not (config.EXPERIMENTS_DIR / args.base / "condition.json").exists():
        raise SystemExit(f"Condition {args.base} does not exist; start it with step1_baseline.py and --change")
    person = current_person()
    levels = levels_of(args.base)
    print(f"Chain {args.base} -> {', '.join(levels) or '(no reflection conditions)'} for {person}")
    new, last = args.new, None
    while True:
        cmd = next_step(args.base, levels, person, new)
        if cmd is None:
            print("Chain complete. Next: python analyze.py  (or tools/run_chain.py ... --new for a further chain)")
            break
        if cmd == last:
            raise SystemExit(f"No progress after: python {' '.join(cmd)}  (see its output above)")
        print("\n>>> python " + " ".join(cmd))
        if args.dry_run:
            break
        subprocess.run([sys.executable, str(ROOT / cmd[0]), *cmd[1:]], check=True, cwd=ROOT)
        new, last = False, cmd                                                # only the first step starts a new chain
