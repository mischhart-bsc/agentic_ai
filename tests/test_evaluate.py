"""Offline test for src/evaluate.py: error categories, result.json, funnel, report quality (Jan's three cases),
notebook conversion and the runner shims (no Ollama, no Docker needed).

Run:  python tests/test_evaluate.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.checker import GT  # noqa: E402
from src.runner import SHIM  # noqa: E402
from src.evaluate import (FUNNEL, error_info, evaluate_version, funnel, py_to_ipynb,  # noqa: E402
                          report_quality_for_dir, summary_line, text_facts)
from src.experiment import Experiment  # noqa: E402
from src.trace import Case  # noqa: E402

TB = 'Traceback (most recent call last):\n  File "/code/code.py", line 13, in <module>\n    x\n'

# final error lines seen in real runs -> expected category
REAL_ERRORS = {
    "KeyError: 'date'": "hallucinated_column",
    'ValueError: Given date string "A" not likely a datetime': "date_parse",
    "TypeError: Object of type int64 is not JSON serializable": "json_serialize",
    "TypeError: float() argument must be a string or a real number, not 'Period'": "period_type",
    "AttributeError: 'Period' object has no attribute 'start'": "period_type",
    "pandas._libs.tslibs.parsing.DateParseError: day is out of range for month: 2026-02-29": "date_parse",
    "TypeError: sum() got an unexpected keyword argument 'level'": "api_misuse",
    "TypeError: Invalid comparison between dtype=datetime64[us] and str": "datetime_type",
    "AttributeError: Can only use .dt accessor with datetimelike values. Did you mean: 'at'?": "datetime_type",
    "ValueError: Unknown format code 'd' for object of type 'str'": "format_error",
    "ValueError: The number of FixedLocator locations (6), usually from a call to set_ticks": "plot_error",
    "ValueError: Column 'date' not found in CSV. Please ensure the CSV has a 'date' column.": "hallucinated_column",
    "ValueError: No valid date column found in the dataset.": "hallucinated_column",
    "ValueError: No flare strength column found (class or goes_class).": "hallucinated_column",
    "ValueError: Invalid frequency: M. Failed to parse with error message: ValueError(\"'M' is no longer supported for offsets. Please use 'ME' instead.\")": "api_misuse",
    "failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine": "infra_docker",
}


def test_categories():
    for line, expected in REAL_ERRORS.items():
        got = error_info(TB + line, 1, "")["error_category"]
        assert got == expected, f"{line!r}: expected {expected}, got {got}"

    info = error_info(TB + "KeyError: 'date'", 1, "")
    assert info["error_type"] == "KeyError" and info["error_line"] == 13

    # a KeyError on a column the code creates itself is an internal bug, not an invented column
    code = "df['year'] = df['start_UTC'].dt.year\nother['year']"
    assert error_info(TB + "KeyError: 'year'", 1, code)["error_category"] == "internal_keyerror"
    # ... but converting a column in place does not create it (real case from the blind baseline)
    code = "df['date'] = pd.to_datetime(df['date'])"
    assert error_info(TB + "KeyError: 'date'", 1, code)["error_category"] == "hallucinated_column"
    assert error_info(TB + "KeyError: 'x'", 1, "if df['x'] == 1: pass")["error_category"] == "hallucinated_column"

    assert error_info("", 0, "x") == {}
    assert error_info("no code block found", None, None)["error_category"] == "no_code"
    assert error_info("TIMEOUT nach 120s", -1, "x")["error_category"] == "exec_timeout"


def test_evaluate_version():
    with tempfile.TemporaryDirectory() as tmp:
        exp = Experiment("E01_test", "baseline", {"generate": "x"}, [101], data_context="schema", root=tmp)
        case = Case(exp, 101)

        # an interrupted first attempt must not be counted in the cost
        case.version("v1").log("llm", label="generate", prompt_tokens=999, completion_tokens=999, seconds=99)

        v1 = case.version("v1")
        v1.log("llm", label="generate", prompt_tokens=1300, completion_tokens=1500, seconds=290,
               finish_reason="stop")
        v1.log("exec", exit_code=0, seconds=5)
        perfect = {"n_months": GT["n_months"], "busiest_month": GT["busiest_month"],
                   "busiest_month_count": GT["busiest_month_count"],
                   "flares_per_year": GT["flares_per_year"], "n_strong": GT["n_strong_estimated_MX"],
                   "pct_strong_per_year": GT["pct_strong_per_year"],
                   "strong_share_increasing": GT["strong_share_increasing_full_years"]}
        stdout = "Report text.\nRESULTS_JSON: " + json.dumps(perfect)
        (v1.dir / "outputs" / "a.png").write_bytes(b"png")

        r = evaluate_version(v1, "print(1)", {"exit_code": 0, "stdout": stdout, "stderr": ""})
        assert r["fact_score"] == 1.0 and r["exit_code"] == 0 and r["error_category"] is None
        assert r["n_plots"] == 1 and r["results_json_strict"]
        assert r["cost"] == {"llm_calls": 1, "prompt_tokens": 1300, "completion_tokens": 1500,
                             "llm_seconds": 290.0, "exec_seconds": 5.0, "truncated": False}
        assert (v1.dir / "stdout.txt").read_text(encoding="utf-8") == stdout
        assert exp.is_done(101, "v1")
        print(summary_line(r))

        # LLM timeout: nothing executed, categorized as llm_timeout
        v2 = case.version("2a", parent="E01_test/s101/v1")
        v2.log("llm", label="critique", prompt_tokens=3000, completion_tokens=50, seconds=600,
               finish_reason="wall_timeout")
        r2 = evaluate_version(v2, None, llm_error="TimeoutError")
        assert r2["error_category"] == "llm_timeout" and r2["fact_score"] == 0.0
        assert r2["cost"]["truncated"] and r2["parent"] == "E01_test/s101/v1"
        print(summary_line(r2))


def test_funnel():
    """Depth = number of stages passed in a row; a late stage alone does not count."""
    base = {"llm_error": None, "code_found": True, "exit_code": 0, "results_json_found": True,
            "results_json_strict": True, "checks": {"n_months": True, "busiest_month": False}}
    full_json = "RESULTS_JSON: " + json.dumps({k: 1 for k in ("n_months", "busiest_month", "busiest_month_count",
                "flares_per_year", "n_strong", "pct_strong_per_year", "strong_share_increasing")})
    f = funnel(base, full_json)
    assert f["depth"] == 7 and f["stages"]["any_fact"] and not f["stages"]["all_facts"]   # right up to "some facts"
    assert funnel({**base, "checks": {"n_months": True}}, full_json)["depth"] == 8          # everything right
    assert funnel({**base, "exit_code": 1}, "")["depth"] == 2                                # crashed: code found, did not run
    assert funnel({**base, "exit_code": 1}, full_json)["depth"] == 2                         # later stages do not count after a crash
    assert funnel({**base, "code_found": False, "exit_code": None}, "")["depth"] == 1       # answer without code block
    assert funnel({**base, "llm_error": "TimeoutError", "code_found": False}, "")["depth"] == 0
    assert funnel(base, "RESULTS_JSON: {\"n_months\": 61}")["stages"]["keys_complete"] is False
    assert len(f["stages"]) == len(FUNNEL)


GOLD_CODE = '''
import json
import pandas as pd
import matplotlib.pyplot as plt
df = pd.read_csv("/data/stix_flarelist.csv")
df["start"] = pd.to_datetime(df["start_UTC"], format="ISO8601")
monthly = df.set_index("start").resample("MS").size()
df["strong"] = df["goes_estimated_mean_class"].str[0].isin(["M", "X"])
pct = df.groupby(df["start"].dt.year)["strong"].mean() * 100
increasing = bool(pct.loc[2022:2025].is_monotonic_increasing)
plt.plot(monthly.index, monthly.values)
plt.title("Flares per month"); plt.xlabel("Month"); plt.ylabel("Flares")
plt.savefig("/outputs/monthly.png")
plt.figure(); plt.bar(pct.index, pct.values)
plt.title("Share of strong flares"); plt.xlabel("Year"); plt.ylabel("%")
plt.savefig("/outputs/share.png")
print(f"The busiest month was {monthly.idxmax():%Y-%m} with {monthly.max()} flares.")
'''

GOLD_REPORT = (
    "Between February 2021 and February 2026 the catalogue contains 33076 flares in 61 months. "
    "Monthly flare counts rose strongly with the solar cycle and peaked in 2024-09 with 1724 flares. "
    "Flares per year were 4787 in 2022, 6469 in 2023, 12330 in 2024 and 7662 in 2025. "
    "In total 1637 flares were strong (M or X class). "
    "The yearly share of strong flares was 5.16% in 2022, 5.39% in 2023, 5.16% in 2024 and 3.86% in 2025. "
    "The share of strong flares did not increase steadily; it fluctuated and dropped in 2025. "
    "Note that 2021 and 2026 are partial years, so their values are less reliable."
)

GOLD_JSON = {
    "n_months": GT["n_months"], "busiest_month": GT["busiest_month"],
    "busiest_month_count": GT["busiest_month_count"], "flares_per_year": GT["flares_per_year"],
    "n_strong": GT["n_strong_estimated_MX"], "pct_strong_per_year": GT["pct_strong_per_year"],
    "strong_share_increasing": GT["strong_share_increasing_full_years"],
}

HALLU_CODE = '''
import json
import pandas as pd
df = pd.read_csv("/data/stix_flarelist.csv")
df["t"] = pd.to_datetime(df["peak_UTC"])
df = df[(df["t"] >= "2021-02-01") & (df["t"] <= "2026-02-01")]
df["strong"] = df["GOES_class_time_of_flare"].str.contains("M|X", na=False)
report = ("The monthly number of solar flares showed a steady increase, with the busiest month being "
          "2023-08 with 124 flares. Strong flares rose from 20% to 35% by 2026.")
print(report)
'''

HALLU_REPORT = ("The monthly number of solar flares showed a steady increase, with the busiest month being "
                "2023-08 with 124 flares. Strong flares rose from 20% to 35% by 2026.")

HALLU_JSON = {"n_months": 60, "busiest_month": "2023-08", "busiest_month_count": 124,
              "flares_per_year": {"2021": 45}, "n_strong": 300,
              "pct_strong_per_year": GT["pct_strong_per_year_WRONG_goes_time_col"],
              "strong_share_increasing": True}

CRASH_CODE = 'import pandas as pd\ndf = pd.read_csv("/data/stix_flarelist.csv")\ndf["date"] = pd.to_datetime(df["date"])\n' + "x = 1\n" * 40



def scored(tmp, name, code, stdout, exit_code, stderr="", n_plots=0):
    """Run a made-up version through evaluate_version and return its result['report']."""
    exp = Experiment(f"E_{name}", "baseline", {"generate": "x"}, [101], data_context="schema", root=tmp)
    v = Case(exp, 101).version("v1")
    v.log("llm", label="generate", prompt_tokens=1000, completion_tokens=1000, seconds=1, finish_reason="stop")
    for i in range(n_plots):
        plt.figure()
        plt.plot([1, 2, 3], [3, 1, 2])
        plt.title(f"plot {i}")
        plt.savefig(v.dir / "outputs" / f"p{i}.png")
        plt.close()
    v.save_code(code)                                      # run_code does this in the real flow
    res = {"exit_code": exit_code, "stdout": stdout, "stderr": stderr}
    return evaluate_version(v, code, res)["report"], v


def test_report_quality():
    """Three made-up versions (from Jan's report_eval test): gold, hallucinated, early crash."""
    with tempfile.TemporaryDirectory() as tmp:
        gold, gv = scored(tmp, "gold", GOLD_CODE, GOLD_REPORT + "\nRESULTS_JSON: " + json.dumps(GOLD_JSON), 0, n_plots=2)
        hallu, _ = scored(tmp, "hallu", HALLU_CODE, HALLU_REPORT + "\nRESULTS_JSON: " + json.dumps(HALLU_JSON), 0, n_plots=1)
        crash, _ = scored(tmp, "crash", CRASH_CODE, "", 1,
                          stderr='Traceback:\n  File "/code/code.py", line 3, in <module>\nKeyError: \'date\'')
        again = report_quality_for_dir(gv.dir)              # re-scoring a stored folder gives the same numbers
    for name, ev in (("gold", gold), ("hallu", hallu), ("crash", crash)):
        print(f"{name:<6} overall={ev['overall']}  {ev['dimensions']}")

    d = gold["dimensions"]
    assert d["correctness"] == 1.0 and d["method"] == 1.0 and d["completeness"] >= 0.95, gold["details"]
    assert gold["overall"] >= 0.95
    assert gold["details"]["correctness"]["claims"] == {"busiest_month": True, "strong_share_trend": True}
    assert again["dimensions"] == gold["dimensions"] and again["flags"] == gold["flags"]

    assert hallu["dimensions"]["execution"] == 1.0
    assert hallu["dimensions"]["correctness"] <= 0.2, hallu["details"]["correctness"]
    assert hallu["details"]["correctness"]["claims"] == {"busiest_month": False, "strong_share_trend": False}
    assert "Report-Text fest im Code (nicht aus Ergebnissen erzeugt)" in hallu["flags"]
    # the observed GOES column is only a hint now (both definitions of "strong" are allowed): no score penalty
    assert "Hinweis: Prozente entsprechen der GOES-Spalte der Erdseite" in hallu["flags"]
    assert hallu["details"]["method"]["goes_column"] == 1.0
    assert hallu["overall"] < 0.5

    assert crash["dimensions"]["execution"] < 0.1       # crash in line 3 of ~43
    assert crash["overall"] < hallu["overall"] < gold["overall"]


def test_text_facts():
    """Facts read from the report text (when RESULTS_JSON is missing)."""
    gold = text_facts(GOLD_REPORT)
    assert gold == {"n_months": True, "busiest_month": True, "busiest_month_count": True, "n_strong": True,
                    "strong_share_increasing": True}, gold

    # wrong and typed-in report of a model that never printed RESULTS_JSON
    wrong = text_facts("Between 2021 and 2026 the flare count grew steadily. The peak monthly flare count occurred in "
                       "February 2021, the first year of observation. The proportion of strong flares rose from 2022 to 2025. "
                       "The share of strong flares increased from year to year.")
    assert wrong["busiest_month"] is False and wrong["strong_share_increasing"] is False, wrong
    assert wrong["n_months"] is None and wrong["n_strong"] is None            # the text says nothing about them

    assert set(text_facts("").values()) == {None}                              # no text -> nothing readable
    assert text_facts("There were 60 months in total.")["n_months"] is False   # a wrong number is False, not None
    # the score is part of the correctness details; the JSON-based fact_score is not touched by it
    with tempfile.TemporaryDirectory() as tmp:
        rep, _ = scored(tmp, "tf", GOLD_CODE, GOLD_REPORT, 0, n_plots=2)       # report text but no RESULTS_JSON
    assert rep["details"]["correctness"]["fact_score"] == 0.0
    assert rep["details"]["correctness"]["text_fact_score"] == 1.0


SCRIPT = """# %% [markdown]
# # Title
# some text
# %%
import pandas as pd
x = 1
# %%
print(x)
"""


def test_notebook_conversion():
    nb = json.loads(py_to_ipynb(SCRIPT))
    assert [c["cell_type"] for c in nb["cells"]] == ["markdown", "code", "code"]
    assert "".join(nb["cells"][0]["source"]) == "# Title\nsome text"
    assert "".join(nb["cells"][1]["source"]) == "import pandas as pd\nx = 1"
    assert nb["nbformat"] == 4 and nb["cells"][2]["outputs"] == []
    assert [c["cell_type"] for c in json.loads(py_to_ipynb("print(1)"))["cells"]] == ["code"]  # no marker: one code cell
    with tempfile.TemporaryDirectory() as tmp:           # evaluate_version saves it next to code.py
        exp = Experiment("E_nb", "baseline", {"generate": "x"}, [101], data_context="schema", root=tmp)
        v = Case(exp, 101).version("v1")
        evaluate_version(v, SCRIPT, {"exit_code": 0, "stdout": "", "stderr": ""})
        assert (v.dir / "notebook.ipynb").exists()


def test_shim():
    """The shim text (src/runner.SHIM) in a plain Python process: numpy numbers (also as dict keys) become JSON, display exists."""
    prog = (SHIM + "\nimport json\n"
            "import numpy as np, pandas as pd\n"
            "print(json.dumps({'a': np.int64(3), 'b': np.bool_(True), 'c': pd.Timestamp('2024-01-02'), 'd': np.arange(2), np.int64(7): 1}))\n"
            "display('shown')\n"
            "import io; f = io.StringIO(); json.dump({'n': np.int64(5)}, f); print(f.getvalue())\n")
    root = Path(__file__).resolve().parent.parent
    venv = root / ".venv" / "bin" / "python"
    out = subprocess.run([str(venv) if venv.exists() else sys.executable, "-c", prog], cwd=root, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.splitlines()[0]) == {"a": 3, "b": True, "c": "2024-01-02 00:00:00", "d": [0, 1], "7": 1}
    assert out.stdout.splitlines()[1] == "shown"
    assert json.loads(out.stdout.splitlines()[2]) == {"n": 5}             # json.dump to a file (prompt v3)


if __name__ == "__main__":
    test_categories()
    test_evaluate_version()
    test_funnel()
    test_report_quality()
    test_text_facts()
    test_notebook_conversion()
    test_shim()
    print("OK - evaluate checks passed")
