"""
File for documentation of true facts of the dataset,
helpful for clearing pitfalls of the LLM regarding the research question
"""
import json
import pandas as pd

df = pd.read_csv("data/stix_flarelist.csv", low_memory=False)

# number of flares per month
df["start_UTC"] = pd.to_datetime(df["start_UTC"], format="ISO8601")
df["year"] = df["start_UTC"].dt.year
monthly = df.set_index("start_UTC").resample("MS").size()
n_months = len(monthly)
print(f"Count of months: {n_months}")
print(f"Busiest month: {monthly.idxmax():%Y-%m} ({monthly.max()} flares)")
print(f"Months without flares: {(monthly == 0).sum()}")

# how did it evolve
per_year = df.groupby("year").size()
print("Flares per year:\n", per_year)

# share of strong flares
df["strong"] = df["goes_estimated_mean_class"].str[0].isin(["M", "X"])
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

# --- save as ground truth
facts = {
    "n_months": n_months,
    "busiest_month": f"{monthly.idxmax():%Y-%m}",
    "busiest_month_count": int(monthly.max()),
    "flares_per_year": {int(k): int(v) for k, v in per_year.items()},
    "n_strong_estimated_MX": int(df["strong"].sum()),
    "pct_strong_per_year": {int(k): float(v) for k, v in pct_strong.items()},
    "strong_share_increasing_full_years": bool(increasing),
    "pct_strong_per_year_WRONG_goes_time_col": {int(k): float(v) for k, v in pct_wrong.items()},
}
with open("ground_truth.json", "w") as f:
    json.dump(facts, f, indent=2)
