"""Offline test for src/experiment.py: condition -> runs -> seeds (no Ollama, no Docker needed).

Run:  python tests/test_experiment.py
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from src.experiment import Experiment, case_path, current_person, load, parse_seeds, person_of, resolve, runs_of  # noqa: E402


def test_experiment():
    assert parse_seeds("101-103") == [101, 102, 103]
    assert parse_seeds("101,105") == [101, 105]

    with tempfile.TemporaryDirectory() as tmp:
        prompts = {"generate": "Write a script."}

        # first run of a condition: condition.json + prompts at the condition, run.json + seeds in <person>_1
        exp = Experiment("B1_test", "baseline", prompts, [101, 102], data_context="schema", person="vanessa", root=tmp)
        assert exp.id == "B1_test/vanessa_1" and exp.dir == Path(tmp) / "B1_test" / "vanessa_1"
        assert (Path(tmp) / "B1_test" / "condition.json").exists() and (exp.dir / "run.json").exists()
        assert (Path(tmp) / "B1_test" / "prompts" / "generate.txt").read_text(encoding="utf-8") == "Write a script."
        m = load("B1_test", root=tmp)                         # a condition with one run resolves to that run
        assert m["id"] == "B1_test/vanessa_1" and m["person"] == "vanessa" and m["status"] == "running"
        assert m["prompts"]["generate"].startswith("sha256:") and m["seeds"] == [101, 102]

        # seeds lie directly in the run folder
        assert exp.case_dir(101) == exp.dir / "s101" and case_path("B1_test/vanessa_1", 101, root=tmp) == exp.dir / "s101"
        assert not exp.is_done(101, "v1")
        (exp.case_dir(101) / "v1").mkdir()
        (exp.case_dir(101) / "v1" / "result.json").write_text("{}", encoding="utf-8")
        assert exp.is_done(101, "v1")

        # the same command again resumes the unfinished run, new seeds are appended
        again = Experiment("B1_test", "baseline", prompts, [101, 102, 103], data_context="schema", person="vanessa", root=tmp)
        assert again.id == "B1_test/vanessa_1" and again.seeds == [101, 102, 103]
        again.finish()
        assert load("B1_test/vanessa_1", root=tmp)["status"] == "complete"

        # a finished run is not reopened: a further run needs new_run (--repeat)
        try:
            Experiment("B1_test", "baseline", prompts, [101], data_context="schema", person="vanessa", root=tmp)
            raise AssertionError("complete run was reopened")
        except SystemExit as e:
            assert "--repeat" in str(e) and "vanessa_2" in str(e)
        v2 = Experiment("B1_test", "baseline", prompts, [101], data_context="schema", person="vanessa", new_run=True, root=tmp)
        assert v2.id == "B1_test/vanessa_2"

        # another person runs the same condition: own run, same condition.json
        jan = Experiment("B1_test", "baseline", prompts, [101], data_context="schema", person="jan", root=tmp)
        assert jan.id == "B1_test/jan_1"
        assert runs_of("B1_test", root=tmp) == ["vanessa_1", "vanessa_2", "jan_1"]

        # several runs: a bare condition is ambiguous, a run must be named
        try:
            resolve("B1_test", root=tmp)
            raise AssertionError("ambiguous condition was accepted")
        except SystemExit as e:
            assert "several runs" in str(e)

        # different conditions under the same id: refused, whoever runs it
        try:
            Experiment("B1_test", "baseline", {"generate": "Other prompt."}, [101], data_context="schema", person="mischa", root=tmp)
            raise AssertionError("changed prompt was accepted")
        except ValueError as e:
            assert "prompts" in str(e)
        assert "mischa_1" not in runs_of("B1_test", root=tmp)

        # a reflection run builds on one base RUN; the condition stores the base condition
        r = Experiment("R1_test", "2a", {"critique": "c", "revise": "r"}, [101], base="B1_test/jan_1",
                       data_context="schema", person="jan", root=tmp)
        cond = json.loads((Path(tmp) / "R1_test" / "condition.json").read_text(encoding="utf-8"))
        assert cond["base"] == "B1_test" and load(r.id, root=tmp)["base"] == "B1_test/jan_1"

        # a legacy experiment (flat, experiment.json + cases/) is read as one run
        legacy = Path(tmp) / "_legacy" / "E10_test"
        (legacy / "cases" / "s101").mkdir(parents=True)
        (legacy / "experiment.json").write_text(json.dumps({"id": "E10_test", "level": "baseline",
                                                            "machine": "Surface-Mischa (Windows, 12 CPUs)"}), encoding="utf-8")
        assert resolve("E10_test", root=tmp) == "E10_test"
        assert load("E10_test", root=tmp)["person"] == "mischa"
        assert case_path("E10_test", 101, root=tmp) == legacy / "cases" / "s101"

    # who runs: AGAI_PERSON wins, else the machine name, else a clear error
    assert person_of("MacBook-Air-von-Jan.local (Darwin, 10 CPUs)") == "jan"
    with mock.patch.dict("os.environ", {"AGAI_PERSON": "Vanessa"}):
        assert current_person() == "vanessa"
    with mock.patch.dict("os.environ", {}, clear=True), mock.patch("platform.node", return_value="unknown-pc"):
        try:
            current_person()
            raise AssertionError("unknown machine was accepted")
        except SystemExit as e:
            assert "RUNNERS" in str(e)
    assert set(config.RUNNERS.values()) == {"vanessa", "jan", "mischa"}


if __name__ == "__main__":
    test_experiment()
    print("OK - experiment checks passed")
