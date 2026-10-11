"""Offline test for src/evaluate.py (no Ollama, no Docker needed).

Run:  python tests/test_evaluate.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.checker import GT  # noqa: E402
from src.evaluate import error_info, evaluate_version, summary_line  # noqa: E402
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


if __name__ == "__main__":
    test_categories()
    test_evaluate_version()
    print("OK - evaluate checks passed")
