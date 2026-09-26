"""Trace-Logger: every action = one JSON-Row in runs/<run_id>/trace.jsonl"""
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

import config


class Run:
    def __init__(self, name: str = "run"):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_id = f"{stamp}_{name}_{uuid.uuid4().hex[:4]}"
        self.dir = config.RUNS_DIR / self.run_id
        (self.dir / "code").mkdir(parents=True, exist_ok=True)
        (self.dir / "outputs").mkdir(exist_ok=True)
        self.trace_file = self.dir / "trace.jsonl"
        self.step = 0

    def log(self, kind: str, **fields):
        self.step += 1
        entry = {"run_id": self.run_id, "step": self.step, "kind": kind,
                 "time": datetime.now().isoformat(timespec="seconds"), **fields}
        with open(self.trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def save_code(self, code: str) -> Path:
        path = self.dir / "code" / f"step_{self.step + 1:03d}.py"
        path.write_text(code, encoding="utf-8")
        return path


def timer():
    t0 = time.perf_counter()
    return lambda: round(time.perf_counter() - t0, 2)
