"""Offline test for tools/run_chain.py: which command comes next, for every state of a chain.

Run:  python tests/test_run_chain.py
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("run_chain", ROOT / "tools" / "run_chain.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)


def condition(root, cond, level, base=None):
    (root / cond).mkdir(parents=True, exist_ok=True)
    (root / cond / "condition.json").write_text(json.dumps({"id": cond, "level": level, "base": base}), encoding="utf-8")


def run(root, cond, name, status="complete", base_run=None, started="2026-11-25T10:00:00"):
    (root / cond / name).mkdir(parents=True)
    (root / cond / name / "run.json").write_text(json.dumps({"status": status, "base_run": base_run, "started": started}),
                                                 encoding="utf-8")


def test_next_step():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        condition(root, "B4_strong", "baseline")
        for cond, level in [("R2_2b", "2b"), ("R1_2a", "2a"), ("R3_2c", "2c")]:
            condition(root, cond, level, base="B4_strong")
        condition(root, "B3_shims", "baseline")
        levels = rc.levels_of("B4_strong", root)
        assert levels == ["R1_2a", "R2_2b", "R3_2c"]                         # level order, other chains left out

        step = lambda new=False: rc.next_step("B4_strong", levels, "jan", new, root)   # noqa: E731
        # Vanessa's chain exists; Jan has nothing yet -> Jan starts his own baseline run
        run(root, "B4_strong", "vanessa_1")
        assert step() == ["step1_baseline.py", "--exp", "B4_strong", "--repeat"]
        # Jan's baseline run was interrupted -> resume it
        run(root, "B4_strong", "jan_1", status="running", started="2026-11-26T10:00:00")
        assert step() == ["step1_baseline.py", "--exp", "B4_strong"]
        # finished -> the first level on HIS run, not on Vanessa's
        (root / "B4_strong" / "jan_1" / "run.json").write_text(json.dumps({"status": "complete", "started": "2026-11-26T10:00:00"}))
        run(root, "R1_2a", "vanessa_1", base_run="B4_strong/vanessa_1")
        assert step() == ["step2_reflection.py", "--exp", "R1_2a", "--base", "B4_strong/jan_1", "--repeat"]
        # R1 interrupted -> resume; done -> R2
        run(root, "R1_2a", "jan_1", status="running", base_run="B4_strong/jan_1")
        assert step() == ["step2_reflection.py", "--exp", "R1_2a", "--base", "B4_strong/jan_1"]
        (root / "R1_2a" / "jan_1" / "run.json").write_text(json.dumps({"status": "complete", "base_run": "B4_strong/jan_1"}))
        assert step()[:3] == ["step2_reflection.py", "--exp", "R2_2b"]
        for cond in ("R2_2b", "R3_2c"):
            run(root, cond, "jan_1", base_run="B4_strong/jan_1")
        assert step() is None                                               # chain complete
        assert step(new=True) == ["step1_baseline.py", "--exp", "B4_strong", "--repeat"]   # a further chain


if __name__ == "__main__":
    test_next_step()
    print("OK - run_chain checks passed")
