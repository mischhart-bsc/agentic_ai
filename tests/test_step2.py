"""Offline test for step2_reflection.py: model and docker are simulated, experiments live in a temp dir.

Run:  python tests/test_step2.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import step1_baseline as s1  # noqa: E402
import step2_reflection as s2  # noqa: E402
from src import runner  # noqa: E402
from src.experiment import Experiment  # noqa: E402
from src.trace import Case  # noqa: E402

V1_ANSWER = "```python\nimport pandas as pd\ndf = pd.read_csv('x')\nprint(df['date'])\n```"
V2_ANSWER = "```python\nprint('fixed')\n```"


def fake_chat(run, messages, label="llm_call", **kw):
    answer = {"generate": V1_ANSWER, "critique": "- uses a column 'date' that does not exist",
              "revise": V2_ANSWER}[label]
    run.log("llm", label=label, seed=kw.get("seed"), prompt_tokens=len(messages) * 100,
            completion_tokens=50, seconds=1.0, finish_reason="stop", messages=messages, response=answer)
    return answer


REAL_RUN = subprocess.run


def docker(cmd, **kw):
    if cmd[0] != "docker":                                                   # git etc. run for real
        return REAL_RUN(cmd, **kw)
    mount = next(a for a in cmd if a.endswith(":/code:ro"))                  # the mounted version folder
    code = Path(mount.rsplit(":/code", 1)[0]) / "code.py"
    if "fixed" in code.read_text(encoding="utf-8"):
        return subprocess.CompletedProcess(cmd, 0, "fixed\n", "")
    return subprocess.CompletedProcess(cmd, 1, "", 'Traceback:\n  File "/code/code.py", line 3\nKeyError: \'date\'')


def test_step2():
    with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.object(config, "EXPERIMENTS_DIR", Path(tmp)), \
            mock.patch.object(s1, "chat", side_effect=fake_chat), \
            mock.patch.object(s2, "chat", side_effect=fake_chat) as chat2, \
            mock.patch.object(runner.subprocess, "run", side_effect=docker):
        # baseline with two seeds
        base = Experiment("B1", "baseline", {"generate": s1.PROMPT}, [101, 102], data_context="blind", person="tester")
        for seed in base.seeds:
            s1.generate_v1(Case(base, seed), "PROMPT TEXT")
        base.finish()

        for level in ("2a", "2b", "2c"):
            exp = Experiment(f"R_{level}", level, {"critique": s2.CRITIQUE}, [101], base=base.id,
                             data_context="blind", person="tester")
            v1 = s2.load_v1(base.id, 101)
            assert v1["answer"] == V1_ANSWER and v1["messages"][0]["content"] == "PROMPT TEXT"
            r = s2.reflect(Case(exp, 101), base.id, v1, level)

            assert r["parent"] == "B1/tester_1/s101/v1" and r["version"] == level
            assert r["exit_code"] == 0 and r["cost"]["llm_calls"] == 2      # critique + revise
            d = exp.dir / "s101" / level
            assert (d / "critique.md").read_text(encoding="utf-8").startswith("- uses")
            feedback = (d / "feedback.md").read_text(encoding="utf-8")
            critique_msg = chat2.call_args_list[-2].args[1][-1]["content"]   # what the critic was asked
            if level == "2a":
                assert feedback == "" and critique_msg == s2.CRITIQUE
            else:
                assert "KeyError: 'date'" in feedback and critique_msg.startswith(feedback)
            assert ("Independent check" in feedback) == (level == "2c")

        # the base experiment is not touched by the levels
        assert not (base.dir / "s101" / "2a").exists()

        # a v1 without an answer cannot be reflected on
        with mock.patch.object(s1, "chat", side_effect=TimeoutError("slow")):
            s1.generate_v1(Case(base, 102), "PROMPT TEXT")
        assert s2.load_v1(base.id, 102) is None
        assert json.loads((base.dir / "s102" / "v1" / "result.json")
                          .read_text(encoding="utf-8"))["error_category"] == "llm_timeout"


if __name__ == "__main__":
    test_step2()
    print("OK - step2 checks passed")
