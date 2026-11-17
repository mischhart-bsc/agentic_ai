"""The report helper (src/runner.py: REPORT_HELPER) and its place in the manifest. No Docker, no Ollama needed.

The helper text is run with a local python the same way the container runs it (python -c <helper> ...), with
EDA_OUTPUTS pointing to a temp folder instead of /outputs.

Run:  python tests/test_report_helper.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.checker import check, extract_results  # noqa: E402
from src.experiment import Experiment  # noqa: E402
from src.runner import REPORT_HELPER  # noqa: E402

MODEL_CODE = '''
import numpy as np
import pandas as pd
report("n_months", np.int64(61))
report("busiest_month", pd.Period("2024-09", "M"))
report("flares_per_year", {np.int64(2021): np.int64(694), 2022: 4787})
report("strong_share_increasing", np.bool_(False))
'''


def run_helper(code, out):
    env = {**os.environ, "EDA_OUTPUTS": str(out)}
    return subprocess.run([sys.executable, "-c", REPORT_HELPER + "\n" + code], capture_output=True, text=True, env=env)


def test_report_writes_plain_json():
    with tempfile.TemporaryDirectory() as tmp:
        p = run_helper(MODEL_CODE, tmp)
        assert p.returncode == 0, p.stderr
        assert p.stdout == ""                                   # the helper prints nothing into the report text
        data = json.loads((Path(tmp) / "results.json").read_text(encoding="utf-8"))
        assert data == {"n_months": 61, "busiest_month": "2024-09",
                        "flares_per_year": {"2021": 694, "2022": 4787}, "strong_share_increasing": False}
        # the checker reads exactly this file
        checks = check(extract_results("", tmp))
        assert checks["n_months"] and checks["busiest_month"] and checks["strong_share_increasing"]


def test_report_keeps_earlier_values_and_overwrites_same_key():
    with tempfile.TemporaryDirectory() as tmp:
        p = run_helper('report("a", 1)\nreport("b", 2)\nreport("a", 3)', tmp)
        assert p.returncode == 0, p.stderr
        assert json.loads((Path(tmp) / "results.json").read_text(encoding="utf-8")) == {"a": 3, "b": 2}


def test_manifest_records_helper_and_blocks_resume_with_other_condition():
    with tempfile.TemporaryDirectory() as tmp:
        exp = Experiment("E99_test", "baseline", {"generate": "x"}, [1], data_context="schema",
                         report_helper=True, root=tmp)
        assert exp.manifest["report_helper"] is True and exp.manifest["report_helper_hash"].startswith("sha256:")
        off = Experiment("E98_test", "baseline", {"generate": "x"}, [1], data_context="schema", root=tmp)
        assert off.manifest["report_helper"] is False and off.manifest["report_helper_hash"] is None
        try:
            Experiment("E99_test", "baseline", {"generate": "x"}, [1], data_context="schema", root=tmp)
        except ValueError as e:
            assert "report_helper" in str(e)
        else:
            raise AssertionError("resume with a different report_helper must be refused")


if __name__ == "__main__":
    test_report_writes_plain_json()
    test_report_keeps_earlier_values_and_overwrites_same_key()
    test_manifest_records_helper_and_blocks_resume_with_other_condition()
    print("OK - report helper checks passed")
