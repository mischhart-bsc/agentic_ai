"""LLM-as-a-Judge: subjective rating of the report (scaffold, off by default).

Steps, following the checklist (evaluation framework):
  1. Agree on the rubric below with the group (criteria, scale, meaning of each level).
  2. Rate 5-10 reports yourself:  python analyze.py --exp <id> --human-template
     -> fill in human_scores.csv.
  3. Run the judge on the same reports:   python analyze.py --exp <id> --judge
  4. Measure the agreement:               python analyze.py --agreement
  5. Adjust the prompt until judge and human agree well enough.

The judge does not rate plots (yet): qwen3 cannot read images. That would need a vision model
in Ollama (e.g. qwen2.5vl or gemma3).
"""
import json
import re
from datetime import datetime
from pathlib import Path

import config
from src.checker import GT
from src.llm import chat

JUDGE_MODEL = getattr(config, "JUDGE_MODEL", config.MODEL)
JUDGE_TEMPERATURE = 0.0

# ---------------------------------------------------------------- Rubric
# Scale 1-5 for all criteria. The descriptions are part of the prompt.
RUBRIC = {
    "answers_question": {
        "question": "Does the report answer BOTH parts of the research question "
                    "(monthly evolution AND change of the strong-flare share)?",
        "levels": {1: "answers neither part", 2: "touches one part vaguely",
                   3: "answers one part clearly", 4: "answers both parts, one only vaguely",
                   5: "answers both parts clearly and directly"},
    },
    "factual_consistency": {
        "question": "Are the statements consistent with the REFERENCE FACTS below?",
        "levels": {1: "main conclusions contradict the facts", 2: "several important errors",
                   3: "mostly right, one important error", 4: "only minor deviations",
                   5: "fully consistent with the facts"},
    },
    "clarity": {
        "question": "Is the report clear, well structured and easy to read for a non-expert?",
        "levels": {1: "incomprehensible / raw output", 2: "hard to follow", 3: "understandable",
                   4: "clear and well structured", 5: "very clear, concise, well structured"},
    },
    "evidence": {
        "question": "Are conclusions backed by concrete numbers (counts, percentages, months)?",
        "levels": {1: "no numbers", 2: "numbers without connection to claims",
                   3: "some claims backed", 4: "most claims backed", 5: "every claim backed"},
    },
    "caveats": {
        "question": "Does the report mention limitations (partial years 2021/2026, data caveats)?",
        "levels": {1: "none, overconfident", 2: "hinted", 3: "one limitation mentioned",
                   4: "relevant limitations mentioned", 5: "limitations mentioned and their effect explained"},
    },
}
CRITERIA = list(RUBRIC)


def reference_facts():
    """Short reference facts for the judge (from ground_truth.json)."""
    return (
        f"- {GT['n_months']} calendar months, Feb 2021 - Feb 2026 (2021 and 2026 are partial years)\n"
        f"- busiest month: {GT['busiest_month']} with {GT['busiest_month_count']} flares\n"
        f"- flares per year: {GT['flares_per_year']}\n"
        f"- strong flares (estimated GOES class M or X): {GT['n_strong_estimated_MX']} in total\n"
        f"- % strong per year: {GT['pct_strong_per_year']}\n"
        f"- the strong share does NOT rise every year across the full years 2022-2025 "
        f"(it peaks in 2023 and drops in 2025)"
    )


def build_messages(report):
    rubric = "\n\n".join(
        f"{name}: {c['question']}\n" + "\n".join(f"  {k} = {v}" for k, v in c["levels"].items())
        for name, c in RUBRIC.items())
    system = ("You are a strict reviewer of exploratory data analysis reports. "
              "Score the report with the rubric. Use only the report text and the reference facts. "
              "Answer with ONE JSON object and nothing else.")
    user = (
        "Research question: How did the monthly number of solar flares evolve between Feb 2021 "
        "and Feb 2026, and did the share of strong flares (GOES class M or X) change over the years?\n\n"
        f"REFERENCE FACTS (ground truth):\n{reference_facts()}\n\n"
        f"RUBRIC (each criterion 1-5):\n{rubric}\n\n"
        f"REPORT:\n\"\"\"\n{report.strip()}\n\"\"\"\n\n"
        "Return JSON with exactly these keys: "
        + ", ".join(f'"{c}" (int 1-5)' for c in CRITERIA)
        + ', "justification" (max 3 sentences).'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_scores(text, criteria=CRITERIA):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    out = {}
    for c in criteria:
        try:
            v = int(data.get(c))
        except (TypeError, ValueError):
            return None
        if not 1 <= v <= 5:
            return None
        out[c] = v
    out["justification"] = str(data.get("justification", ""))[:500]
    return out


class JsonlLog:
    """Where src/llm.chat writes its log line for a judge call: one JSON line per event in a .jsonl file."""

    def __init__(self, path):
        self.path = Path(path)

    def log(self, kind, **fields):
        entry = {"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, **fields}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ask_judge(run_dir, name, messages, criteria):
    """One judge call through src/llm.chat (hard time limit LLM_MAX_SECONDS, temperature 0).
    Logs to <run_dir>/<name>.jsonl, writes <run_dir>/<name>.json if the answer can be read.
    A failed call (timeout, Ollama down) is returned as an error instead of stopping all other ratings."""
    run_dir = Path(run_dir)
    log = JsonlLog(run_dir / f"{name}.jsonl")
    try:
        text = chat(log, messages, label=name, max_tokens=600, model=JUDGE_MODEL, temperature=JUDGE_TEMPERATURE)
    except Exception as e:                                     # noqa: BLE001
        log.log("error", error_type=type(e).__name__, error=str(e))
        return {"model": JUDGE_MODEL, "scores": None, "error": f"{type(e).__name__}: {e}"}
    scores = parse_scores(text, criteria)
    log.log("scores", scores=scores)
    if scores is None:
        return {"model": JUDGE_MODEL, "scores": None, "error": "unparseable judge answer"}
    mean = round(sum(scores[c] for c in criteria) / len(criteria), 2)
    result = {"model": JUDGE_MODEL, "scores": scores, "mean": mean, "score_0_1": round((mean - 1) / 4, 3)}
    (run_dir / f"{name}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def judge_report(run_dir, report):
    """Rate a report with the LLM. Result -> <run_dir>/judge.json (+ judge.jsonl as log)."""
    if not report.strip():
        return None
    return ask_judge(run_dir, "judge", build_messages(report), CRITERIA)


# ---------------------------------------------------------------- Human vs. judge
def agreement(human_csv, runs_dir):
    """Compare human_scores.csv with judge.json. Returns MAE and the share of |diff|<=1 per criterion."""
    import csv
    rows = list(csv.DictReader(open(human_csv, encoding="utf-8")))
    per = {c: [] for c in CRITERIA}
    for row in rows:
        jf = Path(runs_dir) / row["run_id"] / "judge.json"
        if not jf.exists():
            continue
        js = json.loads(jf.read_text(encoding="utf-8")).get("scores") or {}
        for c in CRITERIA:
            if row.get(c, "").strip() and c in js:
                per[c].append(int(row[c]) - int(js[c]))
    out = {}
    for c, diffs in per.items():
        if diffs:
            out[c] = {"n": len(diffs),
                      "mae": round(sum(abs(d) for d in diffs) / len(diffs), 2),
                      "within_1": round(sum(abs(d) <= 1 for d in diffs) / len(diffs), 2),
                      "bias_judge_minus_human": round(-sum(diffs) / len(diffs), 2)}
    return out
