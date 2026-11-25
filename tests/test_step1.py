"""Offline test for step1_baseline.py: model answer and docker call are simulated.

Run:  python tests/test_step1.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import step1_baseline as s1  # noqa: E402
from src import runner  # noqa: E402
from src.experiment import Experiment  # noqa: E402
from src.trace import Case  # noqa: E402

ANSWER = "Here is the script:\n```python\nprint('report')\n```\n"


def fake_chat(run, messages, label="llm_call", **kw):
    run.log("llm", label=label, seed=kw.get("seed"), prompt_tokens=100, completion_tokens=50,
            seconds=1.0, finish_reason="stop", messages=messages, response=ANSWER)
    return ANSWER


def test_step1():
    docker_ok = subprocess.CompletedProcess(args=[], returncode=1, stdout="",
                                            stderr="Traceback:\n  File \"/code/code.py\", line 3\nKeyError: 'date'")
    with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.object(s1, "chat", side_effect=fake_chat) as chat, \
            mock.patch.object(runner.subprocess, "run", return_value=docker_ok):
        prompt, schema = s1.build_prompt(use_schema=True)
        assert "{SCHEMA}" not in prompt and "column | dtype" in prompt
        exp = Experiment("E01_test", "baseline", {"generate": s1.PROMPT, "schema": schema}, [101, 102],
                         data_context="schema", person="tester", root=tmp)

        r = s1.generate_v1(Case(exp, 101), prompt)
        assert chat.call_args.kwargs["seed"] == 101                      # seed reaches the LLM call
        assert r["error_category"] == "hallucinated_column" and r["code_found"]
        v1 = exp.dir / "s101" / "v1"
        assert {p.name for p in v1.iterdir()} >= {"response.md", "code.py", "stdout.txt", "stderr.txt",
                                                  "outputs", "result.json"}
        assert (v1 / "code.py").read_text(encoding="utf-8") == "print('report')\n"

        # LLM failure: recorded, no exception
        with mock.patch.object(s1, "chat", side_effect=TimeoutError("too slow")):
            r = s1.generate_v1(Case(exp, 102), prompt)
        assert r["error_category"] == "llm_timeout" and exp.is_done(102, "v1")
        kinds = [json.loads(l)["kind"] for l in
                 (exp.dir / "s102" / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
        assert kinds == ["version_start", "error", "result"]


if __name__ == "__main__":
    test_step1()
    print("OK - step1 checks passed")
