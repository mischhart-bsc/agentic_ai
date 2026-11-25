"""Trace-Logger: every action = one JSON line in <condition>/<run>/s<seed>/trace.jsonl

Case    = one seed inside one run (owns trace.jsonl)
Version = one code version of a case (v1, 2a, ...): its own folder, its own outputs/, its own result.json
"""
import json
import time
from datetime import datetime
import shutil


class Case:
    """ One seed inside one experiment. """

    def __init__(self, experiment, seed):
        self.experiment = experiment
        self.seed = seed
        self.dir = experiment.case_dir(seed)
        self.trace_file = self.dir / "trace.jsonl"
        # continue the step numbering if the case was interrupted before
        self.step = (len(self.trace_file.read_text(encoding="utf-8").splitlines()) if self.trace_file.exists() else 0)

    def log(self, kind, version=None, stage=None, **fields):
        self.step += 1
        entry = {"experiment": self.experiment.id, "seed": self.seed, "version": version, 
                 "stage": stage, "step": self.step, "kind": kind, "time": datetime.now().isoformat(timespec="seconds"), **fields}
        
        with open(self.trace_file, "a", encoding="utf-8") as f: f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def version(self, name, parent=None):
        """ Start a new version. A leftover folder from an interrupted attempt is cleared first. """
        return Version(self, name, parent)

class Version:
    """ One code version of a case: its own folder, its own outputs, its own result"""

    def __init__(self, case, name, parent=None):
        self.case = case
        self.name = name
        self.parent = parent
        self.dir = case.dir / name
        if self.dir.exists(): # interrupted before result.json was written -> start clean
            shutil.rmtree(self.dir)
        (self.dir / "outputs").mkdir(parents=True)
        self.case.log("version_start", version=name, parent=parent)

    def log(self, kind, stage=None, **fields):
        # chat() passes label="generate" / "critique" / ...; use it as the stage
        stage = stage or fields.get("label")
        return self.case.log(kind, version=self.name, stage=stage, **fields)

    def save(self, filename, text):
        """ Save a readable artifact next to the code, e.g. response.md, critique.md, feedback.md """
        path = self.dir / filename
        path.write_text(text or "", encoding="utf-8")
        return path

    def save_code(self, code):
        """ Called by run_code(): the code is executed from this file. """
        return self.save("code.py", code)

    def write_result(self, result):
        """ Last step of a version: result.json marks it as done (experiment.is_done). """
        result = {"experiment": self.case.experiment.id, "seed": self.case.seed, "version": self.name, "parent": self.parent, **result}
        self.save("result.json", json.dumps(result, indent=2, ensure_ascii=False, default=str))
        # experiment/seed/version are part of every trace line already
        self.log("result", stage="evaluate", **{k: v for k, v in result.items() if k not in ("experiment", "seed", "version")})
        return result

def timer():
    t0 = time.perf_counter()
    return lambda: round(time.perf_counter() - t0, 2)
