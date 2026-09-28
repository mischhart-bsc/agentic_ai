"""Objective checker: compares the model's RESULTS_JSON with ground_truth.json."""
import json
import re

import config

GT = json.loads((config.ROOT / "ground_truth.json").read_text(encoding="utf-8"))

# model key -> ground-truth key
KEYS = {
    "n_months": "n_months",
    "busiest_month": "busiest_month",
    "busiest_month_count": "busiest_month_count",
    "flares_per_year": "flares_per_year",
    "n_strong": "n_strong_estimated_MX",
    "pct_strong_per_year": "pct_strong_per_year",
    "strong_share_increasing": "strong_share_increasing_full_years",
}


def extract_results(stdout: str):
    """Find the RESULTS_JSON line in the program output. Returns dict or None."""
    m = re.search(r"RESULTS_JSON:\s*(\{.*\})", stdout)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _num_equal(a, b, rel_tol):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(rel_tol * abs(b), 0.05)


def _dict_equal(a, b, rel_tol):
    """Compare {year: value} dicts; keys may be str or int."""
    if not isinstance(a, dict):
        return False
    a = {str(k)[:4]: v for k, v in a.items()}
    b = {str(k): v for k, v in b.items()}
    return set(a) == set(b) and all(_num_equal(a[k], b[k], rel_tol) for k in b)


def check(results):
    """Return {key: True/False/None}. None = fact not in ground truth (skipped)."""
    out = {}
    for mk, gk in KEYS.items():
        if gk not in GT:
            out[mk] = None
            continue
        truth = GT[gk]
        val = (results or {}).get(mk)
        if isinstance(truth, dict):
            out[mk] = _dict_equal(val, truth, rel_tol=0.01)
        elif isinstance(truth, bool):
            out[mk] = isinstance(val, bool) and val == truth
        elif isinstance(truth, str):
            out[mk] = isinstance(val, str) and val.strip()[:7] == truth
        else:
            out[mk] = _num_equal(val, truth, rel_tol=0.005)
    return out


def score(checks):
    """Share of checked facts that are correct (skipped facts are ignored)."""
    valid = [v for v in checks.values() if v is not None]
    return round(sum(valid) / len(valid), 3) if valid else 0.0
