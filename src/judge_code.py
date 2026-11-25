"""LLM judge for the generated CODE (subjective, per step).

The report judge (src/judge.py) rates the final text. This one rates a single step on the way there:
the Python script the model wrote. It judges the code as written and NOT whether it crashed
(exit code is measured separately, objectively), so both metrics stay independent.

Run via:  python analyze.py --exp <run id> --judge-code
Writes judge_code.json (+ judge_code.jsonl as log) into each version folder, e.g. B4_strong/vanessa_1/s101/v1/.
Reuses model, temperature, parser and the call (src/llm.chat with its time limit) of src/judge.py.
"""
from pathlib import Path

from src.judge import ask_judge

# Scale 1-5 for all criteria. The level descriptions are part of the prompt.
RUBRIC = {
    "column_choice": {
        "question": "Does the code use columns that really exist in the file, and a sensible one for "
                    "the time axis and for the flare class?",
        "levels": {1: "invents column names (e.g. 'date', 'class')", 2: "some real, some invented columns",
                   3: "real columns, but a poor choice for time or class",
                   4: "real columns, one questionable choice", 5: "real, sensible columns throughout"},
    },
    "data_handling": {
        "question": "Does the code handle the data types correctly (parse only real time columns as dates, "
                    "take the class letter from the class text, deal with missing values)?",
        "levels": {1: "misparses columns (e.g. class text as date) or ignores types",
                   2: "several handling errors", 3: "basic handling, important cases missed",
                   4: "mostly correct, a minor case missed", 5: "correct types, missing values handled"},
    },
    "covers_question": {
        "question": "Does the code compute BOTH parts of the research question (monthly counts AND share of "
                    "strong flares per year) over the whole period?",
        "levels": {1: "computes neither", 2: "computes one part incompletely", 3: "computes one part fully",
                   4: "computes both, period or years incomplete", 5: "computes both over the whole period"},
    },
    "report_from_data": {
        "question": "Is the printed report built from computed variables, rather than text with numbers "
                    "typed in before anything is computed?",
        "levels": {1: "all numbers hard-coded", 2: "mostly hard-coded", 3: "mixed",
                   4: "mostly computed", 5: "every number comes from the computation"},
    },
    "plot_code": {
        "question": "Does the code save sensible plots to /outputs/ (labelled axes, title, no plt.show())?",
        "levels": {1: "no plots", 2: "plot code present but unsuitable", 3: "plot saved, little labelling",
                   4: "plot saved and labelled", 5: "clear, labelled plot(s) that fit the question"},
    },
}
CRITERIA = list(RUBRIC)

# Only facts about the file's structure, never numbers from ground_truth.json (no leaking of answers).
FILE_FACTS = (
    "- time columns: start_UTC, end_UTC, peak_UTC (text, ISO 8601); nothing else is a date\n"
    "- class columns: GOES_class_time_of_flare and goes_estimated_mean_class are TEXT like 'M1.2' "
    "(letter + number), not dates; some values are missing\n"
    "- there are no columns named 'date', 'time' or 'class'"
)


def build_messages(code):
    rubric = "\n\n".join(
        f"{name}: {c['question']}\n" + "\n".join(f"  {k} = {v}" for k, v in c["levels"].items())
        for name, c in RUBRIC.items())
    system = ("You are a strict reviewer of Python data-analysis code. Score the code with the rubric. "
              "Judge the code as written; do not judge whether it crashed. "
              "Answer with ONE JSON object and nothing else.")
    user = (
        "Task given to the author: write ONE script that analyses /data/stix_flarelist.csv (solar flares) "
        "and answers: how did the monthly number of flares evolve from Feb 2021 to Feb 2026, and did the "
        "share of strong flares (GOES class M or X) change over the years?\n\n"
        f"FACTS ABOUT THE FILE:\n{FILE_FACTS}\n\n"
        f"RUBRIC (each criterion 1-5):\n{rubric}\n\n"
        f"CODE:\n```python\n{code.strip()}\n```\n\n"
        "Return JSON with exactly these keys: "
        + ", ".join(f'"{c}" (int 1-5)' for c in CRITERIA)
        + ', "justification" (max 3 sentences).'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def last_code(run_dir):
    """The generated script of a folder: code.py of a version folder (experiments/), else the newest
    code/step_*.py of an old run; None if there is none."""
    single = Path(run_dir) / "code.py"
    if single.exists():
        return single.read_text(encoding="utf-8")
    files = sorted((Path(run_dir) / "code").glob("step_*.py"))
    return files[-1].read_text(encoding="utf-8") if files else None


def judge_code(run_dir):
    """Rate the generated code of one version folder -> <version folder>/judge_code.json."""
    code = last_code(run_dir)
    if not code:
        return None
    return ask_judge(run_dir, "judge_code", build_messages(code), CRITERIA)
