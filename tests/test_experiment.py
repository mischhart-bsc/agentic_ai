"""Offline test for src/experiment.py (no Ollama, no Docker needed).

Run:  python tests/test_experiment.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.experiment import Experiment, load, parse_seeds  # noqa: E402


def test_experiment():
    assert parse_seeds("101-103") == [101, 102, 103]
    assert parse_seeds("101,105") == [101, 105]

    with tempfile.TemporaryDirectory() as tmp:
        prompts = {"generate": "Write a script."}

        # create: manifest, prompt copy, cases folder
        exp = Experiment("E01_test", "baseline", prompts, [101, 102], data_context="schema", root=tmp)
        m = load("E01_test", root=tmp)
        assert m["status"] == "running" and m["seeds"] == [101, 102]
        assert m["prompts"]["generate"].startswith("sha256:")
        assert (exp.dir / "prompts" / "generate.txt").read_text(encoding="utf-8") == "Write a script."

        # a seed/version with a result.json counts as done
        assert not exp.is_done(101, "v1")
        (exp.case_dir(101) / "v1").mkdir()
        (exp.case_dir(101) / "v1" / "result.json").write_text("{}", encoding="utf-8")
        assert exp.is_done(101, "v1")

        exp.finish()
        assert load("E01_test", root=tmp)["status"] == "complete"

        # resume with the same conditions: allowed, new seeds are appended
        exp2 = Experiment("E01_test", "baseline", prompts, [101, 102, 103], data_context="schema", root=tmp)
        assert exp2.seeds == [101, 102, 103] and exp2.manifest["status"] == "running"

        # resume with a changed prompt: refused
        try:
            Experiment("E01_test", "baseline", {"generate": "Other prompt."}, [101],
                       data_context="schema", root=tmp)
            raise AssertionError("changed prompt was accepted")
        except ValueError as e:
            assert "prompts" in str(e)

        # a reflection level that builds on a base
        Experiment("E02_test", "2a", {"critique": "c", "revise": "r"}, [101], base="E01_test",
                   data_context="schema", root=tmp)
        assert load("E02_test", root=tmp)["base"] == "E01_test"


if __name__ == "__main__":
    test_experiment()
    print("OK - experiment checks passed")
