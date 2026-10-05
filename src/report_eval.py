"""Objektive Bewertung der Qualität eines Runs (ohne LLM).

Ein Run (runs/<run_id>/) wird in fuenf Dimensionen bewertet, jede mit Score 0..1:

  execution     Lief der Code? exit 0 = 1.0; Absturz = 0.5 * Anteil des Codes, der vor
                dem Absturz lief (Zeile im Traceback / Anzahl Zeilen); kein Code = 0.
  completeness  Ist alles da? RESULTS_JSON vorhanden, alle Felder mit richtigem Typ,
                Report-Text mit 5-10 Saetzen, die geforderten Themen angesprochen, Plots.
  correctness   Stimmen die Zahlen? JSON vs. Ground Truth (fact_score), Zahlen im Text
                vs. Ground Truth (text_precision), Kernaussagen im Text (claims).
  method        Hat der Code die richtigen Entscheidungen getroffen? Statische Checks am
                generierten Code (richtige Spalten, Klassenbuchstabe, Zeitraum, ...).
  plots         Formale Plot-Qualitaet: Dateien lesbar und nicht leer, Achsen/Titel gesetzt.

overall = gewichtetes Mittel (WEIGHTS); Dimensionen mit None werden ignoriert.
Zusaetzlich liefert jede Bewertung eine Liste 'flags' mit lesbaren Fehlerkategorien
(fuer die Fehlerliste) und alle Einzelmetriken.

Subjektive Kriterien (Layout, Verstaendlichkeit, Plot-Qualitaet) -> src/judge.py
"""
import ast
import json
import re
from pathlib import Path

from src.checker import GT, check, extract_results, score, strict_json_ok

# ---------------------------------------------------------------- Konfiguration
WEIGHTS = {
    "execution": 0.15,
    "completeness": 0.25,
    "correctness": 0.35,
    "method": 0.15,
    "plots": 0.10,
}

# Gewichte der Code-Checks innerhalb der Dimension 'method'
METHOD_WEIGHTS = {
    "time_column": 2, "goes_column": 2, "class_letter": 1, "no_misparse": 1,
    "full_period": 1, "trend_full_years": 1, "dynamic_report": 1,
}

EXPECTED_PLOTS = 2                      # monatliche Anzahl + Anteil starker Flares
SENTENCES_MIN, SENTENCES_MAX = 5, 10    # Vorgabe im Prompt

# Typen, die im RESULTS_JSON erwartet werden (siehe prompts/step1_baseline.txt)
JSON_SCHEMA = {
    "n_months": "int",
    "busiest_month": "yyyy-mm",
    "busiest_month_count": "int",
    "flares_per_year": "dict",
    "n_strong": "int",
    "pct_strong_per_year": "dict",
    "strong_share_increasing": "bool",
}

# Themen, die ein vollstaendiger Report ansprechen sollte (Regex, case-insensitive)
TOPICS = {
    "monthly_evolution": r"\bmonth(ly|s)?\b",
    "busiest_month": r"\b(busiest|peak\w*|highest|most active|maximum)\b",
    "yearly_counts": r"\b(per year|yearly|annual\w*|each year|by year)\b",
    "strong_share": r"\b(strong|[MX][- ]class|M or X|M/X|M and X)\b",
    "trend_answer": r"\b(increas\w*|decreas\w*|rose|rise|rising|declin\w*|grew|grow\w*|stable|fluctuat\w*)\b",
    "data_caveat": r"\b(partial|incomplete|caveat|limitation\w*|missing|only (?:january|february))\b",
}

YEARS = set(range(2021, 2027))
MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]

GT_POOL = None  # wird beim ersten Gebrauch gefuellt


# ---------------------------------------------------------------- Hilfsfunktionen
def _flat_numbers(obj):
    if isinstance(obj, bool):
        return []
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in _flat_numbers(v)]
    if isinstance(obj, (list, tuple)):
        return [n for v in obj for n in _flat_numbers(v)]
    if isinstance(obj, (int, float)):
        return [float(obj)]
    return []


def _gt_pool():
    global GT_POOL
    if GT_POOL is None:
        GT_POOL = _flat_numbers({k: v for k, v in GT.items() if "WRONG" not in k})
    return GT_POOL


def _matches(n, pool, rel=0.02, abs_tol=0.1):
    return any(abs(n - g) <= max(rel * abs(g), abs_tol) for g in pool)


def _mean(values):
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _weighted(parts):
    """parts: {name: (score_or_None, weight)} -> gewichtetes Mittel ohne None."""
    valid = [(s, w) for s, w in parts.values() if s is not None]
    if not valid:
        return None
    return round(sum(s * w for s, w in valid) / sum(w for _, w in valid), 3)


def report_text(stdout):
    """Der Report = alles, was vor der RESULTS_JSON-Zeile ausgegeben wurde."""
    return (stdout or "").split("RESULTS_JSON:")[0].strip()


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if len(p.split()) >= 3]


def numbers_in(text):
    """Zahlen im Text ohne Jahreszahlen, Monatsangaben (2024-09) und kleine Zaehlwoerter (<= 12)."""
    text = re.sub(r"\b\d{4}-\d{2}\b", " ", text or "")
    out = []
    for x in re.findall(r"(?<![\w.])\d[\d,']*(?:\.\d+)?", text):
        try:
            n = float(x.replace(",", "").replace("'", "").rstrip("."))
        except ValueError:
            continue
        if n in YEARS or (n.is_integer() and n <= 12):
            continue
        out.append(n)
    return out


def _dict_close(a, b, rel=0.01):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    a = {str(k)[:4]: v for k, v in a.items()}
    b = {str(k): v for k, v in b.items()}
    try:
        return set(a) == set(b) and all(abs(float(a[k]) - float(b[k])) <= max(rel * abs(float(b[k])), 0.05) for k in b)
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------- Laden
def load_run(run_dir):
    run_dir = Path(run_dir)
    entries = []
    for line in (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    llm = [e for e in entries if e.get("kind") == "llm"]
    execs = [e for e in entries if e.get("kind") == "exec"]
    result = next((e for e in reversed(entries) if e.get("kind") == "result"), None)
    codes = sorted((run_dir / "code").glob("*.py"))
    return {
        "run_id": run_dir.name,
        "dir": run_dir,
        "config": (result or {}).get("config", "?"),
        "llm": llm,
        "execs": execs,
        "result": result,
        "code": codes[-1].read_text(encoding="utf-8") if codes else "",
        "stdout": execs[-1].get("stdout", "") if execs else "",
        "stderr": execs[-1].get("stderr", "") if execs else "",
        "exit_code": execs[-1].get("exit_code") if execs else None,
        "plots": sorted((run_dir / "outputs").glob("*.png")),
    }


# ---------------------------------------------------------------- Dimensionen
def eval_execution(run, flags):
    code = run["code"]
    truncated = any(e.get("finish_reason") == "length" for e in run["llm"])
    if truncated:
        flags.append("Antwort abgeschnitten (max_tokens)")
    if not code.strip():
        flags.append("kein Code-Block")
        return 0.0, {"code_found": False, "exit_ok": False, "progress": 0.0, "truncated": truncated}
    if run["exit_code"] == 0:
        return 1.0, {"code_found": True, "exit_ok": True, "progress": 1.0, "truncated": truncated}

    n_lines = max(len(code.splitlines()), 1)
    hits = re.findall(r'File "/code/step_\d+\.py", line (\d+)', run["stderr"])
    progress = round(min(int(hits[-1]) / n_lines, 1.0), 3) if hits else 0.0
    last = [l for l in run["stderr"].strip().splitlines() if l and not l.startswith(" ")]
    err = last[-1].split(":")[0] if last else "?"
    if "TIMEOUT" in run["stderr"]:
        err = "Timeout"
    flags.append(f"Absturz: {err}")
    return round(0.5 * progress, 3), {"code_found": True, "exit_ok": False, "progress": progress,
                                      "error": err, "truncated": truncated}


def _json_type_ok(value, kind):
    if kind == "int":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer()
    if kind == "yyyy-mm":
        return isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}", value.strip()) is not None
    if kind == "dict":
        return isinstance(value, dict) and len(value) > 0
    if kind == "bool":
        return isinstance(value, bool)
    return False


def eval_completeness(run, results, text, flags):
    m = {}
    m["json_present"] = results is not None
    m["json_strict"] = strict_json_ok(run["stdout"])
    if results is None:
        m["json_keys"] = 0.0
        flags.append("RESULTS_JSON fehlt/unlesbar")
    else:
        ok = [_json_type_ok(results.get(k), t) for k, t in JSON_SCHEMA.items()]
        m["json_keys"] = round(sum(ok) / len(ok), 3)
        missing = [k for (k, t), good in zip(JSON_SCHEMA.items(), ok) if not good]
        if missing:
            flags.append("JSON-Felder fehlen/falscher Typ: " + ", ".join(missing))

    n_sent = len(sentences(text))
    m["n_sentences"] = n_sent
    if SENTENCES_MIN <= n_sent <= SENTENCES_MAX:
        m["length_ok"] = 1.0
    elif SENTENCES_MIN - 2 <= n_sent <= SENTENCES_MAX + 4:
        m["length_ok"] = 0.5
    else:
        m["length_ok"] = 0.0
    if n_sent == 0:
        flags.append("kein Report-Text")

    covered = {t: bool(re.search(rx, text, re.I)) for t, rx in TOPICS.items()}
    m["topics"] = covered
    m["topic_coverage"] = round(sum(covered.values()) / len(covered), 3)

    m["n_plots"] = len(run["plots"])
    m["plots_present"] = round(min(m["n_plots"], EXPECTED_PLOTS) / EXPECTED_PLOTS, 3)

    s = _mean([float(m["json_present"]), m["json_keys"], m["length_ok"],
               m["topic_coverage"], m["plots_present"]])
    return s, m


def _claim_busiest(sents):
    """Erste Monatsangabe in einem Satz ueber den aktivsten Monat -> 'YYYY-MM' oder None."""
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


NEG_TREND = (r"\b(not|no|never|didn't|did not|without)\b[^.]{0,40}\b(increas|ris|grow|grew)"
             r"|\b(decreas\w*|declin\w*|dropp?\w*|fell|fluctuat\w*|stable|stagnat\w*|inconsistent|no clear|non-monoton\w*)\b")
POS_TREND = r"\b(increas\w*|rise|rose|rising|grow\w*|grew|higher|larger)\b"
SHARE_WORDS = r"\b(strong|share|proportion|fraction|percentage|[MX][- ]class|M or X|M/X)\b"


def _claim_trend(sents):
    """Behauptet der Text, dass der Anteil starker Flares steigt? True/False/None."""
    for s in sents:
        if not re.search(SHARE_WORDS, s, re.I):
            continue
        if re.search(NEG_TREND, s, re.I):
            return False
        if re.search(POS_TREND, s, re.I):
            return True
    return None


def eval_correctness(run, results, text, flags):
    m = {}
    checks = check(results)
    m["checks"] = checks
    m["fact_score"] = score(checks) if results is not None else 0.0
    wrong = [k for k, v in checks.items() if v is False]
    if results is not None and wrong:
        flags.append("falsche JSON-Werte: " + ", ".join(wrong))

    nums = numbers_in(text)
    m["text_numbers"] = len(nums)
    if nums:
        m["text_precision"] = round(sum(_matches(n, _gt_pool()) for n in nums) / len(nums), 3)
        if m["text_precision"] < 0.5:
            flags.append("Zahlen im Report-Text stimmen nicht mit den Daten")
        json_pool = _flat_numbers(results) if results else []
        m["text_json_consistency"] = (round(sum(_matches(n, json_pool) for n in nums) / len(nums), 3)
                                      if json_pool else None)
    else:
        m["text_precision"] = None
        m["text_json_consistency"] = None

    sents = sentences(text)
    claims = {}
    b = _claim_busiest(sents)
    if b is not None:
        claims["busiest_month"] = (b == GT["busiest_month"])
        m["claimed_busiest_month"] = b
    t = _claim_trend(sents)
    if t is not None:
        claims["strong_share_trend"] = (t == GT["strong_share_increasing_full_years"])
        m["claimed_strong_increase"] = t
    m["claims"] = claims
    m["claims_score"] = round(sum(claims.values()) / len(claims), 3) if claims else None
    for k, v in claims.items():
        if not v:
            flags.append(f"falsche Aussage im Text: {k}")

    s = _weighted({
        "facts": (m["fact_score"], 0.5),
        "text": (m["text_precision"], 0.25),
        "claims": (m["claims_score"], 0.25),
    })
    return s, m


def _hardcoded_numbers_in_strings(code):
    """True, wenn ein langer String-Literal (kein f-String) Zahlen enthaelt -> Report fest im Code."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    fstring_parts = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                fstring_parts.add(id(v))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in fstring_parts and len(node.value) >= 60
                and numbers_in(node.value)):
            return True
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in fstring_parts and len(node.value) >= 120
                and re.search(r"\b(increas|decreas|busiest|peak)\w*", node.value, re.I)):
            return True   # lange Aussage ohne Zahlen, aber mit fester Schlussfolgerung
    return False


def eval_method(run, results, flags):
    code = run["code"]
    if not code.strip():
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
    uses_wrong = re.search(r"GOES_(class|flux)_time_of_flare", code) is not None
    m["goes_column"] = 1.0 if uses_est else 0.0
    if uses_wrong and not uses_est:
        flags.append("falsche GOES-Spalte (GOES_class_time_of_flare)")
    elif not uses_est:
        flags.append("keine GOES-Spalte verwendet")

    letter = re.search(r"\.str\[0\]|\.str\[:1\]|\.str\.startswith|\^\[?MX|\[0\]\s*in\s*\(?\[?['\"]M", code)
    threshold = re.search(r"mean_flux[^\n]*>=?\s*1e-0?5", code)
    m["class_letter"] = 1.0 if (letter or threshold) else 0.0
    if not (letter or threshold):
        flags.append("Klassenbuchstabe nicht sauber ausgewertet (z.B. contains statt str[0])")

    misparse = re.search(r"to_datetime\(\s*\w+\[\s*['\"]GOES", code, re.I)
    m["no_misparse"] = 0.0 if misparse else 1.0
    if misparse:
        flags.append("GOES-Klasse als Datum geparst")

    truncated_period = re.search(r"2026-02-01|range\(\s*2021\s*,\s*2026\s*\)", code)
    m["full_period"] = 0.0 if truncated_period else 1.0
    if truncated_period:
        flags.append("Zeitraum abgeschnitten (Feb 2026 fehlt)")

    full_years = (r"range\(\s*2022\s*,\s*2026\s*\)|between\(\s*2022\s*,\s*2025\s*\)"
                  r"|2022\s*:\s*2025|\[\s*2022\s*,\s*2023\s*,\s*2024\s*,\s*2025\s*\]")
    m["trend_full_years"] = 1.0 if re.search(full_years, code) else 0.0
    if not m["trend_full_years"]:
        flags.append("Trend nicht ueber volle Jahre 2022-2025")

    hard = _hardcoded_numbers_in_strings(code)
    m["dynamic_report"] = None if hard is None else (0.0 if hard else 1.0)
    if hard:
        flags.append("Report-Text fest im Code (nicht aus Ergebnissen erzeugt)")

    # Diagnose ohne Score
    m["errors_coerce"] = re.search(r"errors\s*=\s*['\"]coerce", code) is not None
    m["pct_matches_wrong_column"] = bool(results) and _dict_close(
        results.get("pct_strong_per_year"), GT.get("pct_strong_per_year_WRONG_goes_time_col"))
    if m["pct_matches_wrong_column"]:
        flags.append("Prozente entsprechen der falschen GOES-Spalte")

    # Spaltenwahl ist die Grundlage fuer alles Weitere -> doppeltes Gewicht
    return _weighted({k: (m[k], w) for k, w in METHOD_WEIGHTS.items()}), m


def eval_plots(run, flags):
    plots = run["plots"]
    m = {"n_plots": len(plots), "files": []}
    if not plots:
        flags.append("keine Plots")
        return 0.0, m

    try:
        import matplotlib.image as mpimg
    except ImportError:
        mpimg = None
    valid = 0
    for p in plots:
        info = {"name": p.name, "bytes": p.stat().st_size}
        ok = info["bytes"] > 0
        if ok and mpimg is not None:
            try:
                img = mpimg.imread(p)
                info["shape"] = list(img.shape)
                info["std"] = round(float(img.std()), 4)
                ok = info["std"] > 0.01          # fast einfarbig = leerer Plot
            except Exception as e:                # noqa: BLE001
                info["error"] = type(e).__name__
                ok = False
        info["ok"] = ok
        valid += ok
        m["files"].append(info)
    m["valid_ratio"] = round(valid / len(plots), 3)
    if valid < len(plots):
        flags.append("Plot-Datei leer oder unlesbar")

    code = run["code"]
    n_save = max(len(re.findall(r"savefig\(", code)), 1)
    n_labels = len(re.findall(r"\.(xlabel|ylabel|title|set_xlabel|set_ylabel|set_title)\(", code))
    m["label_ratio"] = round(min(n_labels / (3 * n_save), 1.0), 3)
    if m["label_ratio"] < 1:
        flags.append("Plots nicht vollstaendig beschriftet")
    if re.search(r"ylim\(\s*0\s*,\s*100\s*\)", code):
        flags.append("Prozent-Achse 0-100 (Unterschiede unsichtbar)")
        m["label_ratio"] = round(m["label_ratio"] * 0.5, 3)

    return _mean([m["valid_ratio"], m["label_ratio"]]), m


# ---------------------------------------------------------------- Gesamt
def evaluate_run(run_dir):
    run = load_run(run_dir)
    flags = []
    results = extract_results(run["stdout"])
    text = report_text(run["stdout"])

    dims, details = {}, {}
    dims["execution"], details["execution"] = eval_execution(run, flags)
    dims["completeness"], details["completeness"] = eval_completeness(run, results, text, flags)
    dims["correctness"], details["correctness"] = eval_correctness(run, results, text, flags)
    dims["method"], details["method"] = eval_method(run, results, flags)
    dims["plots"], details["plots"] = eval_plots(run, flags)

    overall = _weighted({k: (v, WEIGHTS[k]) for k, v in dims.items()})
    return {
        "run_id": run["run_id"],
        "config": run["config"],
        "overall": overall,
        "dimensions": dims,
        "flags": flags,
        "details": details,
        "report_text": text,
    }
