"""
File for documentation of true facts of the dataset,
helpful for clearing pitfalls of the LLM regarding the research question.

Computes every value of ground_truth.json from the data:
  - profile of the data (rows, columns, date range, positions, GOES classes, durations, counts, distance)
  - the 7 facts the checker grades (src/checker.py: KEYS) and the "wrong column" trap

Run:  python step0/facts.py            print the facts and write ground_truth.json
      python step0/facts.py --check    only compare with ground_truth.json, write nothing
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # project folder: config.py, src/

import json
import pandas as pd

import config  # noqa: E402

GT_FILE = config.ROOT / "ground_truth.json"


def compute():
    """All facts of ground_truth.json, in the order of the file."""
    df = pd.read_csv(config.DATA_DIR / config.DATA_FILE, low_memory=False)
    start = pd.to_datetime(df["start_UTC"], format="ISO8601")
    end = pd.to_datetime(df["end_UTC"], format="ISO8601")
    duration_min = (end - start).dt.total_seconds() / 60

    # profile: visible_from_earth is True (front side), False (far side) or empty (imaging failed, no position)
    visible = df["visible_from_earth"].astype(str)
    n_visible, n_far = int((visible == "True").sum()), int((visible == "False").sum())

    # number of flares per month
    df["start_UTC"] = start
    df["year"] = df["start_UTC"].dt.year
    monthly = df.set_index("start_UTC").resample("MS").size()
    print(f"Count of months: {len(monthly)}")
    print(f"Busiest month: {monthly.idxmax():%Y-%m} ({monthly.max()} flares)")
    print(f"Months without flares: {(monthly == 0).sum()}")

    # how did it evolve
    per_year = df.groupby("year").size()
    print("Flares per year:\n", per_year)

    # share of strong flares
    letter = df["goes_estimated_mean_class"].astype("string").str[0]
    df["strong"] = letter.isin(["M", "X"])
    pct_strong = (df.groupby("year")["strong"].mean() * 100).round(2)
    print("% strong per year:\n", pct_strong)

    # did it become larger
    full = pct_strong.loc[2022:2025]
    increasing = full.is_monotonic_increasing          # does every year rise vs. the one before?
    print(f"Share of strong flares rises every full year: {increasing}")

    # trap: the WRONG column gives a different answer
    wrong = df["GOES_class_time_of_flare"].str[0].isin(["M", "X"])
    pct_wrong = (wrong.groupby(df["year"]).mean() * 100).round(2)
    print("% strong per year (WRONG column):\n", pct_wrong)

    return {
        "n_flares": len(df),
        "n_columns": int(df.shape[1] - 2),                 # without the helper columns year and strong
        "first_flare_start": str(start.min()),
        "last_flare_start": str(start.max()),
        "n_duplicate_rows": int(df.drop(columns=["year", "strong"]).duplicated().sum()),
        "n_att_in_true": int(df["att_in"].sum()),
        "n_visible_from_earth": n_visible,
        "n_far_side": n_far,
        "n_no_position": int(len(df) - n_visible - n_far),
        "pct_far_side_of_located": round(100 * n_far / (n_visible + n_far), 2),
        "n_goes_class_missing": int(df["GOES_class_time_of_flare"].isna().sum()),
        "median_duration_min": round(float(duration_min.median()), 2),
        "max_duration_min": round(float(duration_min.max()), 1),
        "median_counts_4_10keV": float(df["4-10 keV"].median()),
        "max_counts_4_10keV": int(df["4-10 keV"].max()),
        "min_distance_AU": round(float(df["solo_position_AU_distance"].min()), 3),
        "max_distance_AU": round(float(df["solo_position_AU_distance"].max()), 3),
        "n_months": len(monthly),
        "busiest_month": f"{monthly.idxmax():%Y-%m}",
        "busiest_month_count": int(monthly.max()),
        "flares_per_year": {str(k): int(v) for k, v in per_year.items()},
        "estimated_class_letter_counts": {str(k): int(v) for k, v in letter.value_counts().items()},
        "n_strong_estimated_MX": int(df["strong"].sum()),
        "pct_strong_per_year": {str(k): float(v) for k, v in pct_strong.items()},
        "strong_share_increasing_full_years": bool(increasing),
        "pct_strong_per_year_WRONG_goes_time_col": {str(k): float(v) for k, v in pct_wrong.items()},
    }


if __name__ == "__main__":
    facts = compute()
    if "--check" in sys.argv:
        stored = json.loads(GT_FILE.read_text(encoding="utf-8"))
        diff = sorted(k for k in set(stored) | set(facts) if stored.get(k) != facts.get(k))
        print("ground_truth.json is reproduced exactly" if not diff else f"DIFFERENT: {diff}")
        raise SystemExit(1 if diff else 0)
    # --- save as ground truth
    with open(GT_FILE, "w") as f:
        json.dump(facts, f, indent=2)
