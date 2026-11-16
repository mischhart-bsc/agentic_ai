"""Evaluate one code version (v1, 2a, ...) after it was executed, and write its result.json.

The same function is used by every step, so baseline and all reflection levels are measured identically.

    res = run_code(version, code)
    result = evaluate_version(version, code, res)
    print(summary_line(result))

result.json contains: the report quality (5 dimensions, flags, overall; moved here from report_eval.py), execution (exit code, error type/category/line), the checker facts (fact_score),
report metrics, number of plots, and the cost of this version (LLM calls, tokens, seconds) read from the trace.
"""
import ast
import json
import re
from pathlib import Path

from src.checker import GT, KEYS, check, extract_results, numbers_in, report_precision, score, strict_json_ok

# Ordered rules: the first matching pattern decides the category.
# Built from the final error lines of all runs up to 2026-10-09 (see tests/test_evaluate.py).
ERROR_RULES = [
    ("infra_docker",       r"docker API|docker run --help|Cannot connect to the Docker daemon"),
    ("exec_timeout",       r"^TIMEOUT"),
    ("json_serialize",     r"is not JSON serializable"),
    ("date_parse",         r"not likely a datetime|DateParseError|Could not parse date|day is out of range"),
    ("period_type",        r"'Period'|Period\b.*not supported"),
    ("datetime_type",      r"Can only use \.dt accessor|Invalid comparison between dtype=datetime"),
    ("api_misuse",         r"unexpected keyword argument|got an unexpected|has no attribute"
                           r"|no longer supported|Invalid frequency"),   # e.g. pandas 3: 'M' -> 'ME'
    ("plot_error",         r"FixedLocator|matplotlib|set_ticks"),
    ("format_error",       r"Unknown format code|format string"),
    # the model's own guard clauses for a column it expected but did not find
    ("hallucinated_column", r"(?i)(no|not found|must have|could not find).{0,40}column"
                            r"|column.{0,40}(not found|missing)"),
]


def _creates_key(code, key):
    """True if the code creates this key itself: an assignment x['key'] = ... whose right side does not
    read x['key'] at the same time. df['date'] = pd.to_datetime(df['date']) does NOT create 'date'."""
    ref = r"\[\s*['\"]" + re.escape(key) + r"['\"]\s*\]"
    for line in (code or "").splitlines():
        m = re.search(ref + r"\s*=(?!=)(.*)", line)
        if m and not re.search(ref, m.group(1)):
            return True
    return False


def error_info(stderr, exit_code, code):
    """Type, message, line and category of the error that ended the script ({} if it ran fine)."""
    if exit_code == 0:
        return {}
    stderr = (stderr or "").strip()
    if exit_code is None:
        return {"error_type": None, "error_message": stderr[:200], "error_line": None,
                "error_category": "no_code"}

    # last line that is not indented = the exception line, e.g. "KeyError: 'date'"
    last = [l for l in stderr.splitlines() if l.strip() and not l.startswith(" ")]
    message = last[-1] if last else stderr[:200]
    error_type = message.split(":")[0].split(".")[-1].strip() if ":" in message else None

    lines = re.findall(r'File "/code/[^"]+", line (\d+)', stderr)
    error_line = int(lines[-1]) if lines else None

    category = next((name for name, rx in ERROR_RULES if re.search(rx, message, re.M)), None)
    if category is None and error_type == "KeyError":
        key = re.search(r"KeyError: ['\"]([^'\"]+)['\"]", message)
        category = ("internal_keyerror" if key and _creates_key(code, key.group(1))
                    else "hallucinated_column")
    if category is None:
        category = f"other:{error_type or 'unknown'}"
    return {"error_type": error_type, "error_message": message[:200], "error_line": error_line,
            "error_category": category}


# ---------------------------------------------------------------- funnel
# Ordered stages of one version. A stage only counts if all stages before it passed ("how far did it get?"),
# so a crash at stage 3 and a crash at stage 6 are no longer both "0 %".
FUNNEL = ("answered", "code_found", "ran", "json_found", "json_strict", "keys_complete", "any_fact", "all_facts")


def facts_of(stdout, out_dir=None):
    """The checker part of result.json: are the results readable (outputs/results.json or a RESULTS_JSON block),
    strictly valid, and which facts are correct. analyze.py recomputes this for old runs too (like report_precision),
    so a change of the parser applies to every experiment; result.json itself is not rewritten."""
    results = extract_results(stdout, out_dir)
    checks = check(results)
    return {"results_json_found": results is not None, "results_json_strict": strict_json_ok(stdout, out_dir),
            "checks": checks, "fact_score": score(checks)}


def funnel(result, stdout, out_dir=None):
    """Which stages of FUNNEL did this version pass, and how many in a row (depth, 0..8).
    result  the result dict of evaluate_version (without the funnel)   stdout  the stdout of the executed code"""
    results = extract_results(stdout, out_dir) or {}
    checks = result.get("checks") or {}
    valid = [v for v in checks.values() if v is not None]
    stages = {
        "answered": not result.get("llm_error"),                         # the LLM returned an answer
        "code_found": bool(result.get("code_found")),                    # the answer had a python block
        "ran": result.get("exit_code") == 0,                             # the script finished without error
        "json_found": bool(result.get("results_json_found")),            # a RESULTS_JSON line could be read
        "json_strict": bool(result.get("results_json_strict")),          # ... and it is valid JSON
        "keys_complete": all(k in results for k in KEYS),                # all 7 requested keys are there
        "any_fact": any(valid),                                          # at least one value is correct
        "all_facts": bool(valid) and all(valid),                         # every value is correct
    }
    depth = 0
    for ok in stages.values():
        if not ok:
            break
        depth += 1
    return {"stages": stages, "depth": depth}


def funnel_for_dir(version_dir):
    """The funnel of an already evaluated version folder (reads result.json and stdout.txt)."""
    d = Path(version_dir)
    result = json.loads((d / "result.json").read_text(encoding="utf-8"))
    out = d / "stdout.txt"
    stdout = out.read_text(encoding="utf-8") if out.exists() else ""
    return funnel({**result, **facts_of(stdout, d / "outputs")}, stdout, d / "outputs")


def facts_for_dir(version_dir):
    """facts_of() of an already evaluated version folder (reads stdout.txt and outputs/)."""
    d = Path(version_dir)
    out = d / "stdout.txt"
    return facts_of(out.read_text(encoding="utf-8") if out.exists() else "", d / "outputs")


# ---------------------------------------------------------------- notebook
def py_to_ipynb(code):
    """Turn a script in the '# %%' cell format into a Jupyter notebook (code only, no outputs).
        # %% [markdown]   -> markdown cell, the leading '# ' of every line is removed
        # %%              -> code cell          (text before the first marker becomes a code cell)"""
    cells, kind, lines = [], "code", []

    def flush():
        text = "\n".join(lines).strip("\n")
        if not text.strip():
            return
        if kind == "markdown":
            text = "\n".join(l[2:] if l.startswith("# ") else l.lstrip("#") for l in text.splitlines())
        src = text.splitlines(keepends=True)
        if src and src[-1].endswith("\n"):
            src[-1] = src[-1].rstrip("\n")
        cell = {"cell_type": kind, "metadata": {}, "source": src}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        cells.append(cell)

    for line in code.splitlines():
        if line.startswith("# %%"):
            flush()
            kind, lines = ("markdown" if "[markdown]" in line else "code"), []
        else:
            lines.append(line)
    flush()
    return json.dumps({"cells": cells, "nbformat": 4, "nbformat_minor": 5,
                       "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}}},
                      indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- report quality (5 dimensions, 0..1)
# Moved here from src/report_eval.py (Jan). The parts that the funnel / error_info / checker already do (exit code,
# JSON found / strict, fact score, error category) are read from the result instead of being computed a second time.
#   execution     did the code run? crash = 0.5 * share of the script that ran before the crash
#   completeness  RESULTS_JSON with the right types, report of 5-10 sentences, topics mentioned, plots
#   correctness   JSON vs ground truth (fact_score), numbers in the text, claims in the text
#   method        static checks of the code (columns, class letter, period, report text computed or typed in)
#   plots         files readable and not empty, axes and titles set
# Subjective criteria (layout, readability) -> src/judge.py
WEIGHTS = {"execution": 0.15, "completeness": 0.25, "correctness": 0.35, "method": 0.15, "plots": 0.10}

# weight of every code check inside 'method'; 0 = shown as a hint only, no effect on the score
METHOD_WEIGHTS = {"time_column": 2, "goes_column": 0, "class_letter": 1, "no_misparse": 1,
                  "full_period": 1, "trend_full_years": 1, "dynamic_report": 1}

EXPECTED_PLOTS = 2                      # monthly number + share of strong flares
SENTENCES_MIN, SENTENCES_MAX = 5, 10    # asked for in the prompt

JSON_SCHEMA = {"n_months": "int", "busiest_month": "yyyy-mm", "busiest_month_count": "int", "flares_per_year": "dict",
               "n_strong": "int", "pct_strong_per_year": "dict", "strong_share_increasing": "bool"}

TOPICS = {   # what a complete report mentions (regex, case-insensitive)
    "monthly_evolution": r"\bmonth(ly|s)?\b",
    "busiest_month": r"\b(busiest|peak\w*|highest|most active|maximum)\b",
    "yearly_counts": r"\b(per year|yearly|annual\w*|each year|by year)\b",
    "strong_share": r"\b(strong|[MX][- ]class|M or X|M/X|M and X)\b",
    "trend_answer": r"\b(increas\w*|decreas\w*|rose|rise|rising|declin\w*|grew|grow\w*|stable|fluctuat\w*)\b",
    "data_caveat": r"\b(partial|incomplete|caveat|limitation\w*|missing|only (?:january|february))\b",
}
MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]
NEG_TREND = (r"\b(not|no|never|didn't|did not|without)\b[^.]{0,40}\b(increas|ris|grow|grew)"
             r"|\b(decreas\w*|declin\w*|dropp?\w*|fell|fluctuat\w*|stable|stagnat\w*|inconsistent|no clear|non-monoton\w*)\b")
POS_TREND = r"\b(increas\w*|rise|rose|rising|grow\w*|grew|higher|larger)\b"
SHARE_WORDS = r"\b(strong|share|proportion|fraction|percentage|[MX][- ]class|M or X|M/X)\b"


def _flat_numbers(obj):
    if isinstance(obj, bool):
        return []
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in _flat_numbers(v)]
    if isinstance(obj, (list, tuple)):
        return [n for v in obj for n in _flat_numbers(v)]
    return [float(obj)] if isinstance(obj, (int, float)) else []


def _matches(n, pool, rel=0.02, abs_tol=0.1):
    return any(abs(n - g) <= max(rel * abs(g), abs_tol) for g in pool)


def _mean(values):
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _weighted(parts):
    """{name: (score or None, weight)} -> weighted mean without the None entries."""
    valid = [(s, w) for s, w in parts.values() if s is not None and w]
    return round(sum(s * w for s, w in valid) / sum(w for _, w in valid), 3) if valid else None


def report_text(stdout):
    """The report = everything printed before the RESULTS_JSON line (with or without ':')."""
    return (stdout or "").split("RESULTS_JSON")[0].strip()


def sentences(text):
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", text or "") if len(p.split()) >= 3]


def _dict_close(a, b, rel=0.01):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    a, b = {str(k)[:4]: v for k, v in a.items()}, {str(k): v for k, v in b.items()}
    try:
        return set(a) == set(b) and all(abs(float(a[k]) - float(b[k])) <= max(rel * abs(float(b[k])), 0.05) for k in b)
    except (TypeError, ValueError):
        return False


def _json_type_ok(value, kind):
    if kind == "int":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer()
    if kind == "yyyy-mm":
        return isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}", value.strip()) is not None
    if kind == "dict":
        return isinstance(value, dict) and len(value) > 0
    return isinstance(value, bool) if kind == "bool" else False


def _eval_execution(code, result, flags):
    if result.get("cost", {}).get("truncated"):
        flags.append("Antwort abgeschnitten (max_tokens)")
    if not (code or "").strip():
        flags.append("kein Code-Block")
        return 0.0, {"code_found": False, "progress": 0.0}
    if result.get("exit_code") == 0:
        return 1.0, {"code_found": True, "progress": 1.0}
    n_lines = max(len(code.splitlines()), 1)
    progress = round(min((result.get("error_line") or 0) / n_lines, 1.0), 3)
    return round(0.5 * progress, 3), {"code_found": True, "progress": progress}


def _eval_completeness(results, text, result, n_plots, flags):
    m = {"json_present": results is not None, "json_strict": bool(result.get("results_json_strict"))}
    if results is None:
        m["json_keys"] = 0.0
        flags.append("RESULTS_JSON fehlt/unlesbar")
    else:
        ok = [_json_type_ok(results.get(k), t) for k, t in JSON_SCHEMA.items()]
        m["json_keys"] = round(sum(ok) / len(ok), 3)
        missing = [k for (k, _), good in zip(JSON_SCHEMA.items(), ok) if not good]
        if missing:
            flags.append("JSON-Felder fehlen/falscher Typ: " + ", ".join(missing))
    n_sent = len(sentences(text))
    m["n_sentences"] = n_sent
    m["length_ok"] = (1.0 if SENTENCES_MIN <= n_sent <= SENTENCES_MAX
                      else 0.5 if SENTENCES_MIN - 2 <= n_sent <= SENTENCES_MAX + 4 else 0.0)
    if n_sent == 0:
        flags.append("kein Report-Text")
    m["topics"] = {t: bool(re.search(rx, text, re.I)) for t, rx in TOPICS.items()}
    m["topic_coverage"] = round(sum(m["topics"].values()) / len(TOPICS), 3)
    m["n_plots"] = n_plots
    m["plots_present"] = round(min(n_plots, EXPECTED_PLOTS) / EXPECTED_PLOTS, 3)
    return _mean([float(m["json_present"]), m["json_keys"], m["length_ok"], m["topic_coverage"], m["plots_present"]]), m


def _claim_busiest(sents):
    """First month named in a sentence about the busiest month -> 'YYYY-MM' or None."""
    for s in sents:
        if not re.search(TOPICS["busiest_month"], s, re.I):
            continue
        m = re.search(r"\b(\d{4})-(\d{2})\b", s)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        m = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{4})\b", s, re.I)
        if m:
            return f"{m.group(2)}-{MONTHS.index(m.group(1).lower()) + 1:02d}"
    return None


def _claim_trend(sents):
    """Does the text say the share of strong flares rises? True / False / None (no statement)."""
    for s in sents:
        if not re.search(SHARE_WORDS, s, re.I):
            continue
        if re.search(NEG_TREND, s, re.I):
            return False
        if re.search(POS_TREND, s, re.I):
            return True
    return None


def _busiest_sentence(sents):
    return next((s for s in sents if re.search(TOPICS["busiest_month"], s, re.I)
                 and (re.search(r"\b\d{4}-\d{2}\b", s) or re.search(r"\b(" + "|".join(MONTHS) + r")\s+\d{4}\b", s, re.I))), None)


def _as_number(x):
    return float(x.replace(",", "").replace("'", ""))


def text_claims(text):
    """What the report TEXT states about the requested facts, as values ({key: value or None}); None = not stated.
    busiest_month_count is the list of numbers in the sentence about the busiest month."""
    sents = sentences(text)
    m = re.search(r"\b(\d{2,3})\s+(?:calendar\s+)?months?\b", text or "", re.I)
    sent = _busiest_sentence(sents)
    n_strong = (re.search(r"(\d[\d,']{2,})\s+(?:\w+\s+){0,3}?strong", text or "", re.I)
                or re.search(r"strong\s+(?:\w+\s+){0,3}?(?:was|were|is|are|:)\s*(\d[\d,']{2,})", text or "", re.I))
    return {"n_months": int(_as_number(m.group(1))) if m else None,
            "busiest_month": _claim_busiest(sents),
            "busiest_month_count": numbers_in(sent) if sent and numbers_in(sent) else None,
            "n_strong": _as_number(n_strong.group(1)) if n_strong else None,
            "strong_share_increasing": _claim_trend(sents)}


def text_facts(text):
    """The facts of RESULTS_JSON that can be read from the report TEXT, compared with the ground truth.
    Used when the model did not print RESULTS_JSON (the fact score of the JSON is then blind, not zero by analysis).
    {key: True / False / None}; None = the text says nothing that can be read for this key.
    Not readable from prose: flares_per_year, pct_strong_per_year (tables of numbers)."""
    c = text_claims(text)
    near = lambda x, truth: abs(x - truth) <= 0.005 * truth      # noqa: E731
    return {
        "n_months": None if c["n_months"] is None else c["n_months"] == GT["n_months"],
        "busiest_month": None if c["busiest_month"] is None else c["busiest_month"] == GT["busiest_month"],
        "busiest_month_count": (None if c["busiest_month_count"] is None
                                else any(near(n, GT["busiest_month_count"]) for n in c["busiest_month_count"])),
        "n_strong": None if c["n_strong"] is None else near(c["n_strong"], GT["n_strong_estimated_MX"]),
        "strong_share_increasing": (None if c["strong_share_increasing"] is None
                                    else c["strong_share_increasing"] == GT["strong_share_increasing_full_years"]),
    }


def _eval_correctness(results, text, result, flags):
    m = {"checks": result.get("checks") or {}, "fact_score": result.get("fact_score") or 0.0}
    wrong = [k for k, v in m["checks"].items() if v is False]
    if results is not None and wrong:
        flags.append("falsche JSON-Werte: " + ", ".join(wrong))
    nums = numbers_in(text)
    m["text_numbers"] = len(nums)
    m["text_precision"] = report_precision(text)                # one implementation: src/checker.report_precision (always fresh)
    json_pool = _flat_numbers(results) if results else []
    m["text_json_consistency"] = (round(sum(_matches(n, json_pool) for n in nums) / len(nums), 3)
                                  if nums and json_pool else None)
    if m["text_precision"] is not None and m["text_precision"] < 0.5:
        flags.append("Zahlen im Report-Text stimmen nicht mit den Daten")
    sents, claims = sentences(text), {}
    busiest = _claim_busiest(sents)
    if busiest is not None:
        claims["busiest_month"] = busiest == GT["busiest_month"]
        m["claimed_busiest_month"] = busiest
    trend = _claim_trend(sents)
    if trend is not None:
        claims["strong_share_trend"] = trend == GT["strong_share_increasing_full_years"]
        m["claimed_strong_increase"] = trend
    m["claims"] = claims
    m["claims_score"] = round(sum(claims.values()) / len(claims), 3) if claims else None
    m["text_facts"] = text_facts(text)                       # same facts as RESULTS_JSON, read from the prose
    readable = [v for v in m["text_facts"].values() if v is not None]
    m["text_fact_score"] = round(sum(readable) / len(readable), 3) if readable else None
    flags += [f"falsche Aussage im Text: {k}" for k, ok in claims.items() if not ok]
    return _weighted({"facts": (m["fact_score"], 0.5), "text": (m["text_precision"], 0.25),
                      "claims": (m["claims_score"], 0.25)}), m


def _hardcoded_report(code):
    """True if a long string literal (not an f-string) holds numbers or a fixed conclusion -> report typed into the code."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    in_fstring = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in in_fstring:
            if len(node.value) >= 60 and numbers_in(node.value):
                return True
            if len(node.value) >= 120 and re.search(r"\b(increas|decreas|busiest|peak)\w*", node.value, re.I):
                return True
    return False


def _eval_method(code, results, flags):
    if not (code or "").strip():
        return None, {}
    m = {}
    if "start_UTC" in code:
        m["time_column"] = 1.0
    elif "peak_UTC" in code:
        m["time_column"] = 0.5
        flags.append("zaehlt nach peak_UTC statt start_UTC")
    else:
        m["time_column"] = 0.0
        flags.append("keine echte Zeitspalte verwendet")

    uses_est = re.search(r"goes_estimated_mean_(class|flux)", code) is not None
    uses_obs = re.search(r"GOES_(class|flux)_time_of_flare", code) is not None
    m["goes_column"] = 1.0 if (uses_est or uses_obs) else 0.0
    if uses_obs and not uses_est:        # hint only (weight 0): both definitions of "strong" are allowed
        flags.append("Hinweis: GOES_class_time_of_flare (nur Erdseite) statt STIX-Schaetzung")
    elif not (uses_est or uses_obs):
        flags.append("keine GOES-Spalte verwendet")

    letter = re.search(r"\.str\[0\]|\.str\[:1\]|\.str\.startswith|\^\[?MX|\[0\]\s*in\s*\(?\[?['\"]M", code)
    threshold = re.search(r"(mean_)?flux[^\n]*>=?\s*1e-0?5", code)
    m["class_letter"] = 1.0 if (letter or threshold) else 0.0
    if not (letter or threshold):
        flags.append("Klassenbuchstabe nicht sauber ausgewertet (z.B. contains statt str[0])")

    misparse = re.search(r"to_datetime\(\s*\w+\[\s*['\"]GOES", code, re.I)
    m["no_misparse"] = 0.0 if misparse else 1.0
    if misparse:
        flags.append("GOES-Klasse als Datum geparst")

    cut = re.search(r"2026-02-01|range\(\s*2021\s*,\s*2026\s*\)", code)
    m["full_period"] = 0.0 if cut else 1.0
    if cut:
        flags.append("Zeitraum abgeschnitten (Feb 2026 fehlt)")

    full_years = (r"range\(\s*2022\s*,\s*2026\s*\)|between\(\s*2022\s*,\s*2025\s*\)"
                  r"|2022\s*:\s*2025|\[\s*2022\s*,\s*2023\s*,\s*2024\s*,\s*2025\s*\]")
    m["trend_full_years"] = 1.0 if re.search(full_years, code) else 0.0
    if not m["trend_full_years"]:
        flags.append("Trend nicht ueber volle Jahre 2022-2025")

    hard = _hardcoded_report(code)
    m["dynamic_report"] = None if hard is None else (0.0 if hard else 1.0)
    if hard:
        flags.append("Report-Text fest im Code (nicht aus Ergebnissen erzeugt)")

    m["errors_coerce"] = re.search(r"errors\s*=\s*['\"]coerce", code) is not None       # diagnosis, no score
    m["pct_matches_obs_column"] = bool(results) and _dict_close(
        results.get("pct_strong_per_year"), GT.get("pct_strong_per_year_WRONG_goes_time_col"))
    if m["pct_matches_obs_column"]:
        flags.append("Hinweis: Prozente entsprechen der GOES-Spalte der Erdseite")
    return _weighted({k: (m[k], w) for k, w in METHOD_WEIGHTS.items()}), m


def _eval_plots(plot_files, code, flags):
    m = {"n_plots": len(plot_files), "files": []}
    if not plot_files:
        flags.append("keine Plots")
        return 0.0, m
    try:
        import matplotlib.image as mpimg
    except ImportError:
        mpimg = None
    valid = 0
    for p in plot_files:
        info = {"name": p.name, "bytes": p.stat().st_size}
        ok = info["bytes"] > 0
        if ok and mpimg is not None:
            try:
                img = mpimg.imread(p)
                info["std"] = round(float(img.std()), 4)
                ok = info["std"] > 0.01              # almost one colour = empty plot
            except Exception as e:                    # noqa: BLE001
                info["error"] = type(e).__name__
                ok = False
        info["ok"] = ok
        valid += ok
        m["files"].append(info)
    m["valid_ratio"] = round(valid / len(plot_files), 3)
    if valid < len(plot_files):
        flags.append("Plot-Datei leer oder unlesbar")
    n_save = max(len(re.findall(r"savefig\(", code or "")), 1)
    n_labels = len(re.findall(r"\.(xlabel|ylabel|title|set_xlabel|set_ylabel|set_title)\(", code or ""))
    m["label_ratio"] = round(min(n_labels / (3 * n_save), 1.0), 3)
    if m["label_ratio"] < 1:
        flags.append("Plots nicht vollstaendig beschriftet")
    if re.search(r"ylim\(\s*0\s*,\s*100\s*\)", code or ""):
        flags.append("Prozent-Achse 0-100 (Unterschiede unsichtbar)")
        m["label_ratio"] = round(m["label_ratio"] * 0.5, 3)
    return _mean([m["valid_ratio"], m["label_ratio"]]), m


def report_quality(code, stdout, plot_files, result, out_dir=None):
    """The five dimensions, the weighted overall score and readable flags for one executed version.
    result = the result dict of evaluate_version so far (exit code, checks, cost, ...)."""
    flags, dims, details = [], {}, {}
    results = extract_results(stdout, out_dir)
    text = report_text(stdout)
    dims["execution"], details["execution"] = _eval_execution(code, result, flags)
    dims["completeness"], details["completeness"] = _eval_completeness(results, text, result, len(plot_files), flags)
    dims["correctness"], details["correctness"] = _eval_correctness(results, text, result, flags)
    dims["method"], details["method"] = _eval_method(code, results, flags)
    dims["plots"], details["plots"] = _eval_plots(plot_files, code, flags)
    overall = _weighted({k: (v, WEIGHTS[k]) for k, v in dims.items()})
    return {"overall": overall, "dimensions": dims, "flags": flags, "details": details, "report_text": text}


def report_quality_for_dir(version_dir):
    """Re-score an already evaluated version folder (reads code.py, stdout.txt, outputs/, result.json)."""
    d = Path(version_dir)
    read = lambda name: (d / name).read_text(encoding="utf-8") if (d / name).exists() else ""   # noqa: E731
    result = {**json.loads(read("result.json") or "{}"), **facts_of(read("stdout.txt"), d / "outputs")}
    return report_quality(read("code.py"), read("stdout.txt"), sorted((d / "outputs").glob("*.png")), result, d / "outputs")


def version_cost(version):
    """LLM and execution cost of this version, read from the case trace.
    Only lines after the LAST start of this version count (an interrupted attempt is not counted twice)."""
    lines = [json.loads(l) for l in version.case.trace_file.read_text(encoding="utf-8").splitlines()]
    mine = [e for e in lines if e.get("version") == version.name]
    starts = [i for i, e in enumerate(mine) if e["kind"] == "version_start"]
    mine = mine[starts[-1]:] if starts else mine
    llm = [e for e in mine if e["kind"] == "llm"]
    execs = [e for e in mine if e["kind"] == "exec"]
    return {
        "llm_calls": len(llm),
        "prompt_tokens": sum(e.get("prompt_tokens") or 0 for e in llm),
        "completion_tokens": sum(e.get("completion_tokens") or 0 for e in llm),
        "llm_seconds": round(sum(e.get("seconds") or 0 for e in llm), 1),
        "exec_seconds": round(sum(e.get("seconds") or 0 for e in execs), 1),
        "truncated": any(e.get("finish_reason") in ("length", "wall_timeout") for e in llm),
    }


def evaluate_version(version, code, res=None, llm_error=None):
    """
    version    trace.Version that was just generated (and executed)
    code       the extracted code, or None if the answer had no code block
    res        result of run_code(), or None if nothing was executed
    llm_error  name of the exception if an LLM call failed (e.g. 'TimeoutError'); then nothing was executed
    """
    res = res or {"exit_code": None, "stdout": "", "stderr": llm_error or "no code block found"}
    stdout, stderr = res.get("stdout", ""), res.get("stderr", "")
    if code and "# %%" in code:
        version.save("notebook.ipynb", py_to_ipynb(code))        # the result as a notebook (code only)
    version.save("stdout.txt", stdout)
    version.save("stderr.txt", stderr)

    err = error_info(stderr, res.get("exit_code"), code)
    if llm_error:
        err = {"error_type": llm_error, "error_message": stderr[:200], "error_line": None,
               "error_category": "llm_timeout" if "Timeout" in llm_error else "llm_error"}

    out_dir = version.dir / "outputs"
    result = {
        "llm_error": llm_error,
        "code_found": code is not None,
        "exit_code": res.get("exit_code"),
        **{k: err.get(k) for k in ("error_type", "error_category", "error_message", "error_line")},
        **facts_of(stdout, out_dir),
        "report_precision": report_precision(stdout),
        "n_plots": len(list(out_dir.glob("*.png"))),
        "cost": version_cost(version),
    }
    f = funnel(result, stdout, out_dir)
    result["funnel"], result["funnel_depth"] = f["stages"], f["depth"]
    rq = report_quality(code, stdout, sorted(out_dir.glob("*.png")), result, out_dir)
    result["report"] = {k: rq[k] for k in ("overall", "dimensions", "flags", "details")}
    return version.write_result(result)


def summary_line(result):
    """One line for the terminal, e.g.  s101 v1  exit=1 hallucinated_column  facts=0%  plots=0  1347+1514 tok"""
    c = result["cost"]
    status = "ok" if result["exit_code"] == 0 else (result["error_category"] or "?")
    return (f"s{result['seed']} {result['version']:<3} exit={result['exit_code']} {status:<20} "
            f"depth={result['funnel_depth']}/{len(FUNNEL)} facts={result['fact_score']:.0%}  plots={result['n_plots']}  "
            f"{c['prompt_tokens']}+{c['completion_tokens']} tok  {c['llm_seconds']:.0f}s")
