"""Objective checker: compares the model's RESULTS_JSON with ground_truth.json."""
import json
import ast
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


def _find(stdout):
    """Text des Objekts nach 'RESULTS_JSON:' - auch wenn es mehrzeilig ist."""
    stdout = stdout or ""
    i = stdout.find("RESULTS_JSON:")
    if i < 0:
        return None
    start = stdout.find("{", i)
    if start < 0:
        return None
    depth = 0
    for j in range(start, len(stdout)):
        if stdout[j] == "{":
            depth += 1
        elif stdout[j] == "}":
            depth -= 1
            if depth == 0:
                return stdout[start:j + 1]
    return None


def strict_json_ok(stdout):
    """True, wenn RESULTS_JSON gueltiges JSON ist (Format-Metrik)."""
    s = _find(stdout)
    if s is None:
        return False
    try:
        return isinstance(json.loads(s), dict)
    except json.JSONDecodeError:
        return False


def extract_results(stdout):
    """Tolerant: echtes JSON oder Python-Dict-Ausgabe (inkl. numpy-Typen). dict oder None."""
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
    """Alle Zahlen aus der Ground Truth, flach (Werte, nicht Jahres-Schluessel)."""
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in _gt_numbers(v)]
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        return [float(obj)]
    return []


GT_NUMS = _gt_numbers({k: v for k, v in GT.items() if "WRONG" not in k})


def report_precision(stdout):
    """Anteil der Zahlen im Report-Text, die zu einem Ground-Truth-Wert passen.
    None, wenn der Text keine Zahlen enthaelt."""
    text = (stdout or "").split("RESULTS_JSON:")[0]
    text = re.sub(r"\b\d{4}-\d{2}\b", "", text)        # Monate wie 2024-09 entfernen
    nums = [float(x.replace(",", "").replace("'", "").rstrip("."))
            for x in re.findall(r"\d[\d,']*\.?\d*", text)]
    nums = [n for n in nums if n not in YEARS]          # Jahreszahlen ignorieren
    if not nums:
        return None
    ok = sum(any(abs(n - g) <= max(0.02 * abs(g), 0.1) for g in GT_NUMS) for n in nums)
    return round(ok / len(nums), 3)