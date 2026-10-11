"""Offline test for Case/Version in src/trace.py (no Ollama, no Docker needed).

Run:  python tests/test_trace.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import runner  # noqa: E402
from src.experiment import Experiment  # noqa: E402
from src.trace import Case  # noqa: E402


def read_trace(case):
    return [json.loads(line) for line in case.trace_file.read_text(encoding="utf-8").splitlines()]


def test_trace():
    with tempfile.TemporaryDirectory() as tmp:
        exp = Experiment("E01_test", "baseline", {"generate": "x"}, [101], data_context="schema", root=tmp)
        case = Case(exp, 101)

        # a version gets its own folder with outputs/
        v1 = case.version("v1")
        assert (v1.dir / "outputs").is_dir()

        # like chat(): run.log("llm", label=...) -> stage is taken from the label
        v1.log("llm", label="generate", response="```python\nprint(1)\n```")
        v1.save("response.md", "```python\nprint(1)\n```")

        # run_code() works unchanged with a Version (docker call simulated)
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="hello\n", stderr="")
        with mock.patch.object(runner.subprocess, "run", return_value=fake) as docker:
            res = runner.run_code(v1, "print(1)")
        cmd = docker.call_args[0][0]
        assert res["exit_code"] == 0 and res["file"] == "code.py"
        assert (v1.dir / "code.py").read_text(encoding="utf-8") == "print(1)"
        assert f"{(v1.dir / 'outputs').resolve()}:/outputs" in cmd      # plots go to this version only

        assert not exp.is_done(101, "v1")
        v1.write_result({"exit_code": 0, "fact_score": 0.5})
        assert exp.is_done(101, "v1")

        # trace: every line carries experiment, seed, version, stage
        lines = read_trace(case)
        assert [l["kind"] for l in lines] == ["version_start", "llm", "exec", "result"]
        assert [l["stage"] for l in lines] == [None, "generate", None, "evaluate"]
        assert all(l["version"] == "v1" and l["seed"] == 101 for l in lines)
        assert [l["step"] for l in lines] == [1, 2, 3, 4]

        # a second version in the same case, with a parent
        v2 = Case(exp, 101).version("2a", parent="E01_test/s101/v1")   # new Case object = resumed later
        assert read_trace(case)[-1] == {**read_trace(case)[-1], "kind": "version_start", "step": 5,
                                         "version": "2a", "parent": "E01_test/s101/v1"}
        assert v2.dir != v1.dir

        # an interrupted version (no result.json) is cleared when it is started again
        v2.save("code.py", "half")
        v2 = case.version("2a", parent="E01_test/s101/v1")
        assert not (v2.dir / "code.py").exists()


if __name__ == "__main__":
    test_trace()
    print("OK - trace checks passed")
