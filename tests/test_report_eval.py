"""Plausibilitaetstest fuer src/report_eval.py mit drei kuenstlichen Runs.

  gold          korrekter Code, korrekter Report, 2 beschriftete Plots  -> hoher Score
  hallucinated  laeuft durch, aber falsche Spalte + erfundener Report    -> niedriger Score
  crash         stuerzt frueh ab                                          -> sehr niedriger Score

Run:  python tests/test_report_eval.py      (oder: pytest tests/)
Braucht weder Ollama noch Docker.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.checker import GT  # noqa: E402
from src.report_eval import evaluate_run  # noqa: E402

GOLD_CODE = '''
import json
import pandas as pd
import matplotlib.pyplot as plt
df = pd.read_csv("/data/stix_flarelist.csv")
df["start"] = pd.to_datetime(df["start_UTC"], format="ISO8601")
monthly = df.set_index("start").resample("MS").size()
df["strong"] = df["goes_estimated_mean_class"].str[0].isin(["M", "X"])
pct = df.groupby(df["start"].dt.year)["strong"].mean() * 100
increasing = bool(pct.loc[2022:2025].is_monotonic_increasing)
plt.plot(monthly.index, monthly.values)
plt.title("Flares per month"); plt.xlabel("Month"); plt.ylabel("Flares")
plt.savefig("/outputs/monthly.png")
plt.figure(); plt.bar(pct.index, pct.values)
plt.title("Share of strong flares"); plt.xlabel("Year"); plt.ylabel("%")
plt.savefig("/outputs/share.png")
print(f"The busiest month was {monthly.idxmax():%Y-%m} with {monthly.max()} flares.")
'''

GOLD_REPORT = (
    "Between February 2021 and February 2026 the catalogue contains 33076 flares in 61 months. "
    "Monthly flare counts rose strongly with the solar cycle and peaked in 2024-09 with 1724 flares. "
    "Flares per year were 4787 in 2022, 6469 in 2023, 12330 in 2024 and 7662 in 2025. "
    "In total 1637 flares were strong (M or X class). "
    "The yearly share of strong flares was 5.16% in 2022, 5.39% in 2023, 5.16% in 2024 and 3.86% in 2025. "
    "The share of strong flares did not increase steadily; it fluctuated and dropped in 2025. "
    "Note that 2021 and 2026 are partial years, so their values are less reliable."
)

GOLD_JSON = {
    "n_months": GT["n_months"], "busiest_month": GT["busiest_month"],
    "busiest_month_count": GT["busiest_month_count"], "flares_per_year": GT["flares_per_year"],
    "n_strong": GT["n_strong_estimated_MX"], "pct_strong_per_year": GT["pct_strong_per_year"],
    "strong_share_increasing": GT["strong_share_increasing_full_years"],
}

HALLU_CODE = '''
import json
import pandas as pd
df = pd.read_csv("/data/stix_flarelist.csv")
df["t"] = pd.to_datetime(df["peak_UTC"])
df = df[(df["t"] >= "2021-02-01") & (df["t"] <= "2026-02-01")]
df["strong"] = df["GOES_class_time_of_flare"].str.contains("M|X", na=False)
report = ("The monthly number of solar flares showed a steady increase, with the busiest month being "
          "2023-08 with 124 flares. Strong flares rose from 20% to 35% by 2026.")
print(report)
'''

HALLU_REPORT = ("The monthly number of solar flares showed a steady increase, with the busiest month being "
                "2023-08 with 124 flares. Strong flares rose from 20% to 35% by 2026.")

HALLU_JSON = {"n_months": 60, "busiest_month": "2023-08", "busiest_month_count": 124,
              "flares_per_year": {"2021": 45}, "n_strong": 300,
              "pct_strong_per_year": GT["pct_strong_per_year_WRONG_goes_time_col"],
              "strong_share_increasing": True}

CRASH_CODE = 'import pandas as pd\ndf = pd.read_csv("/data/stix_flarelist.csv")\ndf["date"] = pd.to_datetime(df["date"])\n' + "x = 1\n" * 40


def make_run(root, name, code, stdout, exit_code, stderr="", n_plots=0, config_name="test"):
    d = Path(root) / name
    (d / "code").mkdir(parents=True)
    (d / "outputs").mkdir()
    (d / "code" / "step_002.py").write_text(code, encoding="utf-8")
    for i in range(n_plots):
        plt.figure()
        plt.plot([1, 2, 3], [3, 1, 2])
        plt.title(f"plot {i}")
        plt.savefig(d / "outputs" / f"p{i}.png")
        plt.close()
    trace = [
        {"kind": "llm", "finish_reason": "stop", "completion_tokens": 1000},
        {"kind": "exec", "exit_code": exit_code, "stdout": stdout, "stderr": stderr},
        {"kind": "result", "config": config_name},
    ]
    (d / "trace.jsonl").write_text("\n".join(json.dumps(e) for e in trace), encoding="utf-8")
    return d


def run_all():
    with tempfile.TemporaryDirectory() as tmp:
        gold = evaluate_run(make_run(tmp, "gold", GOLD_CODE,
                                     GOLD_REPORT + "\nRESULTS_JSON: " + json.dumps(GOLD_JSON), 0, n_plots=2))
        hallu = evaluate_run(make_run(tmp, "hallu", HALLU_CODE,
                                      HALLU_REPORT + "\nRESULTS_JSON: " + json.dumps(HALLU_JSON), 0, n_plots=1))
        crash = evaluate_run(make_run(tmp, "crash", CRASH_CODE, "", 1,
                                      stderr='Traceback:\n  File "/code/step_002.py", line 3, in <module>\nKeyError: \'date\''))
    return gold, hallu, crash


def test_scores():
    gold, hallu, crash = run_all()
    for ev in (gold, hallu, crash):
        print(f"{ev['run_id']:<6} overall={ev['overall']}  {ev['dimensions']}")
        print("        flags:", ev["flags"])

    # Gold: alles richtig
    assert gold["dimensions"]["correctness"] == 1.0, gold["details"]["correctness"]
    assert gold["dimensions"]["method"] == 1.0, gold["details"]["method"]
    assert gold["dimensions"]["completeness"] >= 0.95, gold["details"]["completeness"]
    assert gold["overall"] >= 0.95
    assert gold["details"]["correctness"]["claims"] == {"busiest_month": True, "strong_share_trend": True}

    # Halluziniert: laeuft, ist aber inhaltlich falsch
    assert hallu["dimensions"]["execution"] == 1.0
    assert hallu["dimensions"]["correctness"] <= 0.2, hallu["details"]["correctness"]
    assert hallu["details"]["correctness"]["claims"] == {"busiest_month": False, "strong_share_trend": False}
    assert "Report-Text fest im Code (nicht aus Ergebnissen erzeugt)" in hallu["flags"]
    assert "Prozente entsprechen der falschen GOES-Spalte" in hallu["flags"]
    assert hallu["overall"] < 0.5

    # Absturz in Zeile 3 von ~43
    assert crash["dimensions"]["execution"] < 0.1
    assert crash["overall"] < hallu["overall"] < gold["overall"]


if __name__ == "__main__":
    test_scores()
    print("\nOK - alle Pruefungen bestanden")
