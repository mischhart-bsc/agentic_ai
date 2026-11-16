"""Objective checker: compares the model's RESULTS_JSON with ground_truth.json."""
import json
import ast
import re
from pathlib import Path

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


RESULTS_FILE = "results.json"      # prompt step1_baseline_v3: the notebook saves its results to /outputs/results.json


def results_file_text(out_dir):
    """Text of outputs/results.json, or None if the code saved no such file."""
    p = Path(out_dir) / RESULTS_FILE if out_dir else None
    return p.read_text(encoding="utf-8", errors="replace") if p and p.is_file() else None


def _find(stdout, strict=False):
    """Text of the object after 'RESULTS_JSON:' - also when it spans several lines.
    strict=False also accepts 'RESULTS_JSON' without ':' and the object on the next line
    (seen in E02-E08: print("RESULTS_JSON", json.dumps(...)) and print("RESULTS_JSON"); print(dict))."""
    stdout = stdout or ""
    m = re.search(r"RESULTS_JSON:\s*\{" if strict else r"RESULTS_JSON\s*:?\s*\{", stdout)
    if not m:
        return None
    start = m.end() - 1
    depth = 0
    for j in range(start, len(stdout)):
        if stdout[j] == "{":
            depth += 1
        elif stdout[j] == "}":
            depth -= 1
            if depth == 0:
                return stdout[start:j + 1]
    return None


def strict_json_ok(stdout, out_dir=None):
    """True if the results are valid JSON (format metric): outputs/results.json, otherwise exactly 'RESULTS_JSON: {...}' in stdout."""
    s = results_file_text(out_dir)
    if s is None:
        s = _find(stdout, strict=True)
    if s is None:
        return False
    try:
        return isinstance(json.loads(s), dict)
    except json.JSONDecodeError:
        return False


def extract_results(stdout, out_dir=None):
    """Tolerant: real JSON or Python dict output (incl. numpy types). A dict or None.
    outputs/results.json wins if it exists; otherwise the RESULTS_JSON block in stdout."""
    s = results_file_text(out_dir)
    if s is None:
        s = _find(stdout)
    if s is None:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    s = re.sub(r"np\.(True|False)_", r"\1", s)        # np.True_ -> True
    s = re.sub(r"np\.\w+\(([^()]*)\)", r"\1", s)      # np.int64(1724) -> 1724
    try:
        v = ast.literal_eval(s)
        return v if isinstance(v, dict) else None
    except (ValueError, SyntaxError):
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


def _dict_credit(a, b, rel_tol):
    """Share of the ground-truth years that the model got right (extra or missing years are not an all-or-nothing failure)."""
    if not isinstance(a, dict):
        return 0.0
    a = {str(k)[:4]: v for k, v in a.items()}
    return sum(k in a and _num_equal(a[k], v, rel_tol) for k, v in b.items()) / len(b)


def credit(results, checks=None):
    """Partial credit per fact, 0..1 (None = skipped). Same tolerances as check(); the difference is only that
    a {year: value} fact earns the share of correct years instead of 0 or 1. check() stays the strict yes/no."""
    checks = check(results) if checks is None else checks
    out = {}
    for mk, gk in KEYS.items():
        if checks.get(mk) is None:
            out[mk] = None
        elif isinstance(GT[gk], dict):
            out[mk] = round(_dict_credit((results or {}).get(mk), {str(k): v for k, v in GT[gk].items()}, 0.01), 3)
        else:
            out[mk] = 1.0 if checks[mk] else 0.0
    return out


def score_partial(credits):
    """Mean partial credit of the checked facts (skipped facts are ignored)."""
    valid = [v for v in credits.values() if v is not None]
    return round(sum(valid) / len(valid), 3) if valid else 0.0


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

YEARS = {2021, 2022, 2023, 2024, 2025, 2026}


def _gt_numbers(obj):
    """All numbers of the ground truth, flat (values, not year keys)."""
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in _gt_numbers(v)]
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        return [float(obj)]
    return []


GT_NUMS = _gt_numbers({k: v for k, v in GT.items() if "WRONG" not in k})


def numbers_in(text):
    """Numbers in a text, without years, months (2024-09) and small counting words (<= 12): '3 months' is no claim."""
    text = re.sub(r"\b\d{4}-\d{2}\b", "", text or "")
    out = []
    for x in re.findall(r"(?<![\w.])\d[\d,']*(?:\.\d+)?", text):
        try:
            n = float(x.replace(",", "").replace("'", "").rstrip("."))
        except ValueError:
            continue
        if n not in YEARS and not (n.is_integer() and n <= 12):
            out.append(n)
    return out


def report_precision(stdout):
    """Share of the numbers in the report text that match a ground-truth value. None if the text has no numbers."""
    nums = numbers_in((stdout or "").split("RESULTS_JSON")[0])
    if not nums:
        return None
    ok = sum(any(abs(n - g) <= max(0.02 * abs(g), 0.1) for g in GT_NUMS) for n in nums)
    return round(ok / len(nums), 3)
