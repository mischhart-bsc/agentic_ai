""" Creates the structure for each experiment to enable tracing and qualitative argumentability.

Condition = WHAT is tested (step + one change, e.g. B4_strong): prompts, schema, shims, model, temperature.
Run       = WHO ran it, WHEN and ON WHICH MACHINE (e.g. vanessa_1): every run uses the same seeds (cases).

experiments/<condition>/
    condition.json          fixed conditions: level, base condition, model, temperature, prompt hashes, shims
    prompts/                copy of every prompt text exactly as it was used
    <person>_<n>/           one run, e.g. vanessa_1, jan_1, mischa_2
        run.json            person, machine, model digest, git commit, base run, seeds, status
        s<seed>/            one folder per seed; filled by trace.Case

Results are averaged in two stages: first over the seeds of a run, then over the runs of a condition.
A reflection run always builds on ONE base run (base_run, e.g. B4_strong/vanessa_1), because it reflects on
exactly those frozen v1s.

Inside the code a run is addressed by its unit id "<condition>/<run>". The old flat experiments in
experiments/_legacy/ (E01-E21, L00-L09: experiment.json + cases/) count as a condition with a single run.

A finished run is never changed. The same command again resumes your unfinished run; a new run of a condition
you already ran needs new_run=True (--repeat). Different conditions under the same id raise an error.
"""

import hashlib
import json
import os
import platform
import re
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

import config
from src.runner import REPORT_HELPER, SHIM

# Conditions that must be identical for every run of a condition
FINGERPRINT_KEYS = ("level", "base", "data_context", "model", "temperature", "max_tokens", "prompts", "runner_shims", "shim_hash",
                    "report_helper", "report_helper_hash")
OLD_DEFAULTS = {"runner_shims": False, "shim_hash": None, "report_helper": False, "report_helper_hash": None}      # manifests written before a key existed
RUN_NAME = re.compile(r"^([a-z]+)_(\d+)$")


def parse_seeds(text):
    """'101-105' -> [101, ..., 105]   '101,103,110' -> [101, 103, 110]"""
    seeds = []
    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-")
            seeds += list(range(int(a), int(b) + 1))
        else:
            seeds.append(int(part))
    return seeds

# turns a prompt into a short fingerprint
def sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]

def git_info():
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=config.ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return None
    commit = git("rev-parse", "--short", "HEAD")
    # generated code inside runs/ and experiments/ is data, not project code
    status = git("status", "--porcelain", "--", "*.py", "prompts", ":(exclude)runs", ":(exclude)experiments")
    return {"git_commit": commit or None, "git_dirty": bool(status) if status is not None else None}

# A model name like qwen3-4b-instruct-16k is only a label on each person’s machine. digest is real fingerprint
def model_digest():
    """ Short digest of the Ollama model, so 'same name, different model' is visible. None if Ollama is off. """
    url = config.OLLAMA_URL.rsplit("/v1", 1)[0] + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            models = json.load(r)["models"]
    except Exception:
        return None
    for m in models:
        if m["name"].split(":")[0] == config.MODEL.split(":")[0]:
            return m["digest"][:12]
    return None


def machine():
    return f"{platform.node()} ({platform.system()}, {os.cpu_count()} CPUs)"


def person_of(machine_text):
    """The person of a machine string as stored in a manifest, e.g. 'Surface-Mischa (Windows, 12 CPUs)' -> 'mischa'."""
    return config.RUNNERS.get((machine_text or "").split(" (")[0])


def current_person():
    """Who runs on this machine: AGAI_PERSON if set, else the machine name looked up in config.RUNNERS."""
    person = os.environ.get("AGAI_PERSON") or config.RUNNERS.get(platform.node())
    if not person:
        raise SystemExit(f"Unknown machine '{platform.node()}': add it to RUNNERS in config.py "
                         f"(or set AGAI_PERSON for this session), so every run is named after the person who ran it.")
    return person.lower()


# ---------------------------------------------------------------- reading the folder structure
def _root(root=None):
    return Path(root or config.EXPERIMENTS_DIR)


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def runs_of(condition, root=None):
    """Run names of a condition, oldest first, e.g. ['vanessa_1', 'jan_1']."""
    d = _root(root) / condition
    runs = [r for r in d.iterdir() if (r / "run.json").exists()] if d.is_dir() else []
    return [r.name for r in sorted(runs, key=lambda r: _read(r / "run.json").get("started") or "")]


def unit_dir(unit_id, root=None):
    """Folder of a run ('B4_strong/vanessa_1') or of a flat legacy experiment ('E10_baseline_v3' in _legacy/)."""
    root = _root(root)
    d = root / unit_id
    if (d / "run.json").exists() or (d / "experiment.json").exists():
        return d
    legacy = root / "_legacy" / unit_id
    if (legacy / "experiment.json").exists():
        return legacy
    raise FileNotFoundError(f"Run or experiment '{unit_id}' not found below {root}")


def case_path(unit_id, seed, root=None):
    """Folder of one seed: <run>/s101 (new structure) or <experiment>/cases/s101 (legacy)."""
    d = unit_dir(unit_id, root)
    return d / "cases" / f"s{seed}" if (d / "cases").is_dir() else d / f"s{seed}"


def resolve(ref, root=None):
    """'B4_strong/vanessa_1' -> itself; 'B4_strong' -> its run if it has exactly one; legacy id -> itself."""
    root = _root(root)
    if "/" in ref:
        unit_dir(ref, root)                           # raises if missing
        return ref
    if (root / ref / "condition.json").exists():
        runs = runs_of(ref, root)
        if len(runs) == 1:
            return f"{ref}/{runs[0]}"
        if not runs:
            raise FileNotFoundError(f"Condition '{ref}' has no run yet")
        raise SystemExit(f"Condition '{ref}' has several runs ({', '.join(runs)}): name one, e.g. {ref}/{runs[0]}")
    unit_dir(ref, root)                               # legacy experiment (raises if missing)
    return ref


def load(ref, root=None):
    """Manifest of one run: condition.json + run.json merged ("id" = unit id, "base" = base run).
    For a legacy experiment: its experiment.json. ref may be a condition with a single run."""
    unit_id = resolve(ref, root)
    d = unit_dir(unit_id, root)
    if (d / "experiment.json").exists():              # legacy: one file, one run
        m = _read(d / "experiment.json")
        return {**m, "condition": m["id"], "run": None, "person": person_of(m.get("machine"))}
    cond, run = _read(d.parent / "condition.json"), _read(d / "run.json")
    return {**cond, **run, "id": unit_id, "condition": cond["id"], "run": d.name,
            "base_condition": cond.get("base"), "base": run.get("base_run")}


class Experiment:
    """One run of a condition. exp.id is the unit id '<condition>/<run>' (it is written into every trace line)."""

    def __init__(self, exp_id, level, prompts, seeds, base=None, data_context=None, note="", change="",
                 runner_shims=False, report_helper=False, person=None, new_run=False, root=None):
        """
        exp_id        the condition, e.g. 'R1_2a' (one step + one change)
        level         'baseline', '2a', '2b', '2c', ...
        prompts       {name: text} of every prompt this experiment uses
        seeds         list of ints, one case per seed
        base          the base RUN this one builds on, e.g. 'B4_strong/vanessa_1' (None for a baseline)
        data_context  'blind' or 'schema'
        runner_shims  True if the code ran with SHIM loaded (display, numpy-safe json)
        report_helper True if the code ran with REPORT_HELPER loaded (report(key, value) writes results.json)
        change        one sentence: what is different from the condition this one is compared with (shown in PERFORMANCE_LOG.md)
        person        who runs it (default: from the machine, see config.RUNNERS)
        new_run       True: start a new run although this person already finished one (--repeat)
        root          folder that holds the experiments (default config.EXPERIMENTS_DIR; tests use a temp dir)
        """
        self.condition = exp_id
        self.cond_dir = _root(root) / exp_id
        self.prompts = prompts
        self.person = (person or current_person()).lower()
        base_condition = base.split("/")[0] if base else None
        self.condition_manifest = {
            "id": exp_id,
            "level": level,
            "base": base_condition,
            "change": change,
            "note": note,
            "data_context": data_context,
            "runner_shims": bool(runner_shims),
            "shim_hash": sha(SHIM) if runner_shims else None,
            "report_helper": bool(report_helper),
            "report_helper_hash": sha(REPORT_HELPER) if report_helper else None,
            "model": config.MODEL,
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
            "prompts": {name: sha(text) for name, text in prompts.items()},
        }
        self.run_manifest = {
            "person": self.person,
            "base_run": base,
            "seeds": list(seeds),
            "model_digest": model_digest(),
            "llm_max_seconds": config.LLM_MAX_SECONDS,
            **git_info(),
            "machine": machine(),
            "ollama_url": config.OLLAMA_URL,          # where the model was requested (no secrets: the key is a dummy)
            "docker_image": config.DOCKER_IMAGE,
            "started": datetime.now().isoformat(timespec="seconds"),
            "finished": None,
            "status": "running",
        }
        self._condition()
        self._run(new_run)

    # -------------------------------------------------- setup
    def _condition(self):
        """Create the condition, or check that it was started with exactly these conditions."""
        path = self.cond_dir / "condition.json"
        if not path.exists():
            (self.cond_dir / "prompts").mkdir(parents=True) # creates prompts and all missing parent folders
            for name, text in self.prompts.items():
                (self.cond_dir / "prompts" / f"{name}.txt").write_text(text, encoding="utf-8")
            path.write_text(json.dumps(self.condition_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            return
        old = _read(path)
        diff = [k for k in FINGERPRINT_KEYS if old.get(k, OLD_DEFAULTS.get(k)) != self.condition_manifest[k]]
        if diff:
            raise ValueError(f"Condition '{self.condition}' already exists with different conditions: "
                             f"{', '.join(diff)}. Use a new experiment id")
        self.condition_manifest = old

    def _run(self, new_run):
        """Resume this person's unfinished run, or start the next one (<person>_<n+1>)."""
        mine = [r for r in runs_of(self.condition, self.cond_dir.parent) if r.split("_")[0] == self.person]
        last = mine[-1] if mine else None
        if last and _read(self.cond_dir / last / "run.json")["status"] != "complete":
            self.run = last
            self._resume()
            return
        if last and not new_run:
            raise SystemExit(f"{self.condition}/{last} is complete. To repeat the condition use --repeat "
                             f"(starts {self.condition}/{self.person}_{int(last.split('_')[1]) + 1}).")
        n = max((int(RUN_NAME.match(r).group(2)) for r in mine if RUN_NAME.match(r)), default=0) + 1
        self.run = f"{self.person}_{n}"
        self.dir.mkdir()
        self._check_model_digest()
        self._write()

    def _resume(self):
        old = _read(self.dir / "run.json")
        if old.get("base_run") != self.run_manifest["base_run"]:
            raise ValueError(f"Run '{self.id}' builds on {old.get('base_run')}, not on {self.run_manifest['base_run']}")
        if old.get("git_commit") != self.run_manifest["git_commit"]:
            print(f"Warning: '{self.id}' was started on commit {old.get('git_commit')}, "
                  f"now {self.run_manifest['git_commit']}")
        new_seeds = [s for s in self.run_manifest["seeds"] if s not in old["seeds"]]
        self.run_manifest = {**old, "seeds": old["seeds"] + new_seeds, "status": "running", "finished": None}
        self._write()

    def _check_model_digest(self):
        """Warn if another run of this condition used a different model file under the same name."""
        for r in runs_of(self.condition, self.cond_dir.parent):
            other = _read(self.cond_dir / r / "run.json").get("model_digest")
            mine = self.run_manifest["model_digest"]
            if other and mine and other != mine:
                print(f"Warning: {self.condition}/{r} used model digest {other}, this run uses {mine}")

    def _write(self):
        (self.dir / "run.json").write_text(json.dumps(self.run_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # -------------------------------------------------- use
    @property
    def id(self):
        return f"{self.condition}/{self.run}"

    @property
    def dir(self):
        return self.cond_dir / self.run

    @property
    def manifest(self):
        """condition + run, merged (the same view as load())."""
        return {**self.condition_manifest, **self.run_manifest, "id": self.id, "condition": self.condition,
                "run": self.run, "base_condition": self.condition_manifest.get("base"),
                "base": self.run_manifest.get("base_run")}

    @property
    def seeds(self):
        return self.run_manifest["seeds"]

    def case_dir(self, seed):
        d = self.dir / f"s{seed}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def is_done(self, seed, version):
        """True if this seed/version already has a result (used to resume after an interruption)"""
        return (self.dir / f"s{seed}" / version / "result.json").exists()

    def finish(self):
        self.run_manifest["status"] = "complete"
        self.run_manifest["finished"] = datetime.now().isoformat(timespec="seconds")
        self._write()


def change_missing(exp_id, change):
    """True if a NEW condition is started without saying what changed (a new run of an existing one is fine)."""
    return not change and not (Path(config.EXPERIMENTS_DIR) / exp_id / "condition.json").exists()
