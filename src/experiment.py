""" Creates the structure for each experiment to enable tracing and qualitative argumentability
Experiment = one set of fixed conditions, run over several seeds (cases)

experiments/<exp_id>/
    experiment.json         manifest: level, base, model, temperature, prompt hashes, git, machine, status
    prompts/                copy of every prompt text exactly as it was used
    cases/s<seed>/          one folder per seed; filled by trace.Case

A finished experiment is never changed. Re-running the same exp_id resumes it (seeds that already have a result are skipped bey the caller);
re-running it with different conditions raises an error.
"""

import hashlib
import json
import os
import platform
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

import config
from src.runner import REPORT_HELPER, SHIM

# Conditions that must be identical when an existing experiment is resumed
FINGERPRINT_KEYS = ("level", "base", "data_context", "model", "temperature", "max_tokens", "prompts", "runner_shims", "shim_hash",
                    "report_helper", "report_helper_hash")
OLD_DEFAULTS = {"runner_shims": False, "shim_hash": None, "report_helper": False, "report_helper_hash": None}      # manifests written before a key existed

def load(exp_id, root=None):
    """Read the manifest of an existing experiment (e.g. the base of a reflection level)."""
    path = Path(root or config.EXPERIMENTS_DIR) / exp_id / "experiment.json"
    if not path.exists():
        raise FileNotFoundError(f"Experiment '{exp_id}' not found ({path})")
    return json.loads(path.read_text(encoding="utf-8"))

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


class Experiment:
    def __init__(self, exp_id, level, prompts, seeds, base=None, data_context=None, note="", change="", runner_shims=False, report_helper=False, root=None):
        """
        exp_id        unique name, e.g. 'R1_2a'
        level         'baseline', '2a', '2b', '2c', ...
        prompts       {name: text} of every prompt this experiment uses
        seeds         list of ints, one case per seed
        base          exp_id of the experiment whose v1 this one builds on (None for a baseline)
        data_context  'blind' or 'schema'
        runner_shims  True if the code ran with SHIM loaded (display, numpy-safe json)
        report_helper True if the code ran with REPORT_HELPER loaded (report(key, value) writes results.json)
        change        one sentence: what is different from the experiment this one is compared with (shown in PERFORMANCE_LOG.md)
        root          folder that holds the experiments (default config.EXPERIMENTS_DIR; tests use a temp dir)
        """
        self.id = exp_id
        self.dir = Path(root or config.EXPERIMENTS_DIR) / exp_id
        self.prompts = prompts
        self.manifest = {
            "id": exp_id,
            "level": level,
            "base": base,
            "change": change,
            "runner_shims": bool(runner_shims),
            "shim_hash": sha(SHIM) if runner_shims else None,
            "report_helper": bool(report_helper),
            "report_helper_hash": sha(REPORT_HELPER) if report_helper else None,
            "note": note,
            "seeds": list(seeds),
            "data_context": data_context,
            "model": config.MODEL,
            "model_digest": model_digest(),
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
            "llm_max_seconds": config.LLM_MAX_SECONDS,
            "prompts": {name: sha(text) for name, text in prompts.items()},
            **git_info(),
            "machine": machine(),
            "ollama_url": config.OLLAMA_URL,          # where the model was requested (no secrets: the key is a dummy)
            "docker_image": config.DOCKER_IMAGE,
            "started": datetime.now().isoformat(timespec="seconds"),
            "finished": None,
            "status": "running"
        }
        if (self.dir / "experiment.json").exists():
            self._resume()
        else:
            self._create()
    # -------------------------------------------------- setup
    def _create(self):
        (self.dir / "prompts").mkdir(parents=True) # creates prompts and all missing parent folders
        (self.dir / "cases").mkdir()
        for name, text in self.prompts.items():
            (self.dir / "prompts" / f"{name}.txt").write_text(text, encoding="utf-8")
        self._write()

    def _resume(self):
        old = json.loads((self.dir / "experiment.json").read_text(encoding="utf-8"))
        diff = [k for k in FINGERPRINT_KEYS if old.get(k, OLD_DEFAULTS.get(k)) != self.manifest[k]] # conditions must match to resume
        if diff:
            raise ValueError(f"Experiment '{self.id}' already exists with different conditions: "
                             f"{', '.join(diff)}. Use a new experiment id")
        if old.get("git_commit") != self.manifest["git_commit"]:
            print(f"Warning: '{self.id}' was started on commit {old.get("git_commit")}, "
                  f" now {self.manifest["git_commit"]}")
        new_seeds = [s for s in self.manifest["seeds"] if s not in old["seeds"]]
        self.manifest = {**old,"seeds": old["seeds"] + new_seeds, "status":"running", "finished":None}
        self._write()

    def _write(self):
        (self.dir / "experiment.json").write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # -------------------------------------------------- use
    @property
    def seeds(self):
        return self.manifest["seeds"]

    def case_dir(self, seed):
        d = self.dir / "cases" / f"s{seed}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def is_done(self, seed, version):
        """True if this seed/version already has a result (used to resume after an interruption)"""
        return (self.dir / "cases" / f"s{seed}" / version / "result.json").exists()

    def finish(self):
        self.manifest["status"] = "complete"
        self.manifest["finished"] = datetime.now().isoformat(timespec="seconds")
        self._write()

def change_missing(exp_id, change):
    """True if a NEW experiment is started without saying what changed (resuming an existing one is fine)."""
    return not change and not (Path(config.EXPERIMENTS_DIR) / exp_id / "experiment.json").exists()
