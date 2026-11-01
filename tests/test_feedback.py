"""Offline test for src/feedback.py (no Ollama, no Docker needed).

Run:  python tests/test_feedback.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.checker import GT  # noqa: E402
from src.feedback import build_feedback, prompt_texts  # noqa: E402


def make_v1(tmp, stdout, stderr, exit_code, plots=0, blank=False):
    d = Path(tmp) / "v1"
    (d / "outputs").mkdir(parents=True)
    (d / "stdout.txt").write_text(stdout, encoding="utf-8")
    (d / "stderr.txt").write_text(stderr, encoding="utf-8")
    (d / "result.json").write_text(json.dumps({"exit_code": exit_code}), encoding="utf-8")
    for i in range(plots):
        plt.figure()
        if not blank:
            plt.plot([1, 2, 3], [3, 1, 2])
        plt.axis("off" if blank else "on")
        plt.savefig(d / "outputs" / f"p{i}.png")
        plt.close()
    return d


def test_feedback():
    assert prompt_texts("2a") == {}
    assert set(prompt_texts("2b")) == {"feedback_2b"}
    assert set(prompt_texts("2c")) == {"feedback_2b", "feedback_2c"}

    with tempfile.TemporaryDirectory() as tmp:
        tb = 'Traceback (most recent call last):\n  File "/code/code.py", line 9\nKeyError: \'date\''
        v1 = make_v1(tmp, "", tb, 1)
        assert build_feedback("2a", v1) == ""                        # reflection alone: nothing extra

        fb = build_feedback("2b", v1)
        assert "Exit code: 1" in fb and "KeyError: 'date'" in fb and "none (no PNG" in fb
        assert "Independent check" not in fb                          # 2b has no external facts

        fb = build_feedback("2c", v1)
        assert "no RESULTS_JSON line was printed" in fb               # 2c = 2b + check

    with tempfile.TemporaryDirectory() as tmp:
        claims = {"n_months": GT["n_months"], "busiest_month": "2021-03", "n_strong": 5}
        v1 = make_v1(tmp, "Report.\nRESULTS_JSON: " + json.dumps(claims), "", 0, plots=2)
        fb = build_feedback("2c", v1)
        assert "n_months (number of months): supported" in fb
        assert "busiest_month (busiest month): REFUTED" in fb
        assert "flares_per_year (flares per year): MISSING" in fb
        assert GT["busiest_month"] not in fb                          # the correct value is never revealed
        assert "p0.png" in fb and "drawn" in fb

    with tempfile.TemporaryDirectory() as tmp:
        v1 = make_v1(tmp, "x", "", 0, plots=1, blank=True)
        assert "appears EMPTY" in build_feedback("2b", v1)


REPORT_WRONG = ("The monthly number of flares grew steadily over 61 months. The peak monthly flare count occurred in "
                "February 2021, the first year of observation. In total 900 flares were strong (M or X class). "
                "The share of strong flares increased from year to year.")


def test_run_observations_and_text_check():
    """2b adds plain observations; 2c checks the claims of the report text when RESULTS_JSON is missing."""
    with tempfile.TemporaryDirectory() as tmp:
        v1 = make_v1(tmp, REPORT_WRONG, "", 0, plots=2)
        fb2b = build_feedback("2b", v1)
        assert "Run observations" in fb2b and "a line starting with RESULTS_JSON: not printed" in fb2b
        assert "plots saved: 2" in fb2b and "sentences" in fb2b
        assert "Independent check" not in fb2b and "REFUTED" not in fb2b      # 2b stays free of external facts

        fb = build_feedback("2c", v1)
        assert "no RESULTS_JSON line was printed" in fb                        # the missing line is named
        assert "busiest month: your text says 2021-02 -> REFUTED" in fb
        assert "number of months: your text says 61 -> supported" in fb
        assert "strong share increasing 2022-2025: your text says the share rises -> REFUTED" in fb
        assert GT["busiest_month"] not in fb and str(GT["n_strong_estimated_MX"]) not in fb   # never the correct values

    with tempfile.TemporaryDirectory() as tmp:
        v1 = make_v1(tmp, "", "", 1)
        assert "nothing was printed to stdout" in build_feedback("2b", v1)
        assert "states none of the checkable facts" in build_feedback("2c", v1)

    # the fixed texts go into the manifest, so a change of the wording is detected
    assert "Run observations" in prompt_texts("2b")["feedback_2b"]
    assert "report TEXT" in prompt_texts("2c")["feedback_2c"]


if __name__ == "__main__":
    test_feedback()
    test_run_observations_and_text_check()
    print("OK - feedback checks passed")
