"""Evaluate one code version (v1, 2a, ...) after it was executed, and write its result.json.

The same function is used by every step, so baseline and all reflection levels are measured identically.

    res = run_code(version, code)
    result = evaluate_version(version, code, res)
    print(summary_line(result))

result.json contains: execution (exit code, error type/category/line), the checker facts (fact_score),
report metrics, number of plots, and the cost of this version (LLM calls, tokens, seconds) read from the trace.
"""
import json
import re

from src.checker import check, extract_results, report_precision, score, strict_json_ok

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
    version.save("stdout.txt", stdout)
    version.save("stderr.txt", stderr)

    err = error_info(stderr, res.get("exit_code"), code)
    if llm_error:
        err = {"error_type": llm_error, "error_message": stderr[:200], "error_line": None,
               "error_category": "llm_timeout" if "Timeout" in llm_error else "llm_error"}

    results = extract_results(stdout)
    checks = check(results)
    result = {
        "llm_error": llm_error,
        "code_found": code is not None,
        "exit_code": res.get("exit_code"),
        **{k: err.get(k) for k in ("error_type", "error_category", "error_message", "error_line")},
        "results_json_found": results is not None,
        "results_json_strict": strict_json_ok(stdout),
        "report_precision": report_precision(stdout),
        "checks": checks,
        "fact_score": score(checks),
        "n_plots": len(list((version.dir / "outputs").glob("*.png"))),
        "cost": version_cost(version),
    }
    return version.write_result(result)


def summary_line(result):
    """One line for the terminal, e.g.  s101 v1  exit=1 hallucinated_column  facts=0%  plots=0  1347+1514 tok"""
    c = result["cost"]
    status = "ok" if result["exit_code"] == 0 else (result["error_category"] or "?")
    return (f"s{result['seed']} {result['version']:<3} exit={result['exit_code']} {status:<20} "
            f"facts={result['fact_score']:.0%}  plots={result['n_plots']}  "
            f"{c['prompt_tokens']}+{c['completion_tokens']} tok  {c['llm_seconds']:.0f}s")
