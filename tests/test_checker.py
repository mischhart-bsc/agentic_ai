"""Calibration test for src/checker.py: a perfect answer must score 1.0, a wrong or empty one 0.0.

Run:  python tests/test_checker.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.checker import GT, check, extract_results, score, strict_json_ok  # noqa: E402


def perfect():
    return {
        "n_months": GT["n_months"],
        "busiest_month": GT["busiest_month"],
        "busiest_month_count": GT["busiest_month_count"],
        "flares_per_year": GT["flares_per_year"],
        "n_strong": GT["n_strong_estimated_MX"],
        "pct_strong_per_year": GT["pct_strong_per_year"],
        "strong_share_increasing": GT["strong_share_increasing_full_years"],
    }


def wrong():
    return {
        "n_months": 60,
        "busiest_month": "2023-01",
        "busiest_month_count": 100,
        "flares_per_year": {"2021": 1, "2022": 2},
        "n_strong": 5,
        "pct_strong_per_year": {"2021": 50.0},
        "strong_share_increasing": not GT["strong_share_increasing_full_years"],
    }


def test_checker():
    assert score(check(perfect())) == 1.0
    assert score(check(wrong())) == 0.0
    assert score(check(None)) == 0.0          # no RESULTS_JSON at all
    assert score(check({})) == 0.0            # empty object

    # int years as keys and a month given as a full date are accepted
    p = perfect()
    p["flares_per_year"] = {int(k): v for k, v in p["flares_per_year"].items()}
    p["busiest_month"] = p["busiest_month"] + "-15"
    assert score(check(p)) == 1.0

    # a value off by more than the tolerance is rejected
    p = perfect()
    p["busiest_month_count"] = round(GT["busiest_month_count"] * 1.05)
    assert check(p)["busiest_month_count"] is False

    # parsing: strict JSON, numpy-style Python dict output, missing line
    line = "RESULTS_JSON: " + json.dumps(perfect())
    assert strict_json_ok(line) and extract_results(line) == perfect()
    np_line = "RESULTS_JSON: {'n_months': np.int64(61), 'strong_share_increasing': np.False_}"
    assert not strict_json_ok(np_line)
    assert extract_results(np_line) == {"n_months": 61, "strong_share_increasing": False}
    assert extract_results("no result line here") is None


if __name__ == "__main__":
    test_checker()
    print("OK - checker calibration passed")
