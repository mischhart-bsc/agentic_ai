"""Move flat experiments (experiments/<id>/experiment.json + cases/) into the run structure:

    experiments/B4_strong/experiment.json + cases/s101 ...
 -> experiments/B4_strong/condition.json            WHAT is tested (fingerprint, prompts, change)
    experiments/B4_strong/prompts/                  unchanged
    experiments/B4_strong/vanessa_1/run.json        WHO / WHEN / WHERE (person from the machine, config.RUNNERS)
    experiments/B4_strong/vanessa_1/s101 ...        the seed folders, moved unchanged

Trace lines and result.json files are NOT rewritten: they keep "experiment": "B4_strong" and
"parent": "B4_strong/s101/v1" as written at the time; analyze.py takes the run from the folder.
A reflection experiment gets base_run = <its base>/<person of the base>_1.
experiments/_legacy/ is not touched.

Run:  python tools/migrate_to_runs.py            dry run: only print what would move
      python tools/migrate_to_runs.py --apply    do it (then: git add -A experiments, git shows renames)
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from src.experiment import OLD_DEFAULTS, person_of  # noqa: E402

CONDITION_KEYS = ("id", "level", "base", "change", "note", "data_context", "runner_shims", "shim_hash",
                  "report_helper", "report_helper_hash", "model", "temperature", "max_tokens", "prompts")
RUN_KEYS = ("seeds", "model_digest", "llm_max_seconds", "git_commit", "git_dirty", "machine", "ollama_url",
            "docker_image", "started", "finished", "status")


def flat_experiments(root):
    """{id: manifest} of the flat experiments directly in root (not _legacy, not yet migrated)."""
    out = {}
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / "experiment.json").exists() and not (d / "condition.json").exists():
            out[d.name] = json.loads((d / "experiment.json").read_text(encoding="utf-8"))
    return out


def plan(root):
    """[(id, run name, condition.json, run.json)] or SystemExit if a machine is unknown."""
    flats = flat_experiments(root)
    steps = []
    for exp_id, m in flats.items():
        person = person_of(m.get("machine"))
        if not person:
            raise SystemExit(f"{exp_id}: machine '{m.get('machine')}' is not in config.RUNNERS")
        base_run = None
        if m.get("base"):
            base_m = flats.get(m["base"])
            if base_m is None:
                raise SystemExit(f"{exp_id}: its base '{m['base']}' is not a flat experiment in {root}")
            base_run = f"{m['base']}/{person_of(base_m.get('machine'))}_1"
        condition = {k: m.get(k, OLD_DEFAULTS.get(k)) for k in CONDITION_KEYS}
        run = {"person": person, "base_run": base_run, **{k: m.get(k) for k in RUN_KEYS},
               "migrated_from": f"experiments/{exp_id}/ (flat layout, moved by tools/migrate_to_runs.py)"}
        steps.append((exp_id, f"{person}_1", condition, run))
    return steps


def apply(root, steps):
    for exp_id, run_name, condition, run in steps:
        d = root / exp_id
        run_dir = d / run_name
        if run_dir.exists():
            raise SystemExit(f"{run_dir} exists already, nothing moved for {exp_id}")
        run_dir.mkdir()
        for case in sorted((d / "cases").iterdir()):
            shutil.move(str(case), str(run_dir / case.name))
        (d / "cases").rmdir()
        (run_dir / "run.json").write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
        (d / "condition.json").write_text(json.dumps(condition, indent=2, ensure_ascii=False), encoding="utf-8")
        (d / "experiment.json").unlink()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="move the folders (default: dry run)")
    ap.add_argument("--root", default=str(config.EXPERIMENTS_DIR), help="experiments folder (tests use a copy)")
    args = ap.parse_args()

    root = Path(args.root)
    steps = plan(root)
    if not steps:
        raise SystemExit("Nothing to migrate: no flat experiments directly in " + str(root))
    for exp_id, run_name, _, run in steps:
        n = len(list((root / exp_id / "cases").glob("s*")))
        base = f"  base run {run['base_run']}" if run["base_run"] else ""
        print(f"{exp_id:<20} -> {exp_id}/{run_name}/   ({n} seeds){base}")
    if not args.apply:
        print("\nDry run. Move with:  python tools/migrate_to_runs.py --apply")
        raise SystemExit(0)
    apply(root, steps)
    print(f"\nMoved {len(steps)} experiments. Next: git add -A experiments  (git records the moves as renames)")
