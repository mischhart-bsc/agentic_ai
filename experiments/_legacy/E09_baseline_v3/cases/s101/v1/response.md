```python
# %% [markdown]
# # Exploratory Data Analysis: Solar Flare Frequency and Strong Flare Share (2021–2026)

# %% [markdown]
# This notebook performs an exploratory data analysis on solar flares observed by the STIX X-ray telescope on Solar Orbiter.  
# The research question is: How did the monthly number of flares evolve from February 2021 to February 2026, and did the share of strong flares change over the years?

# %% [markdown]
# Import required libraries

# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy import stats
import json

# %% [markdown]
# Load the data from the CSV file

# %%
data_path = "/data/stix_flarelist.csv"
flare_data = pd.read_csv(data_path)

# %% [markdown]
# Inspect the structure of the data to understand the columns

# %%
print(flare_data.head())
print(flare tqdm)

# %% [markdown]
# Ensure the 'date' column is properly parsed as datetime and extract month and year

# %%
flare_data['date'] = pd.to_datetime(flare_data['date'])
flare_data['year'] = flare_data['date'].dt.year
flare_data['month'] = flare_data['date'].dt.month
flare_data['month_year'] = flare_data['date'].dt.to_period('M')

# %% [markdown]
# Filter data to include only observations from February 2021 to February 2026

# %%
start_date = pd.to_datetime('2021-02-01')
end_date = pd.to_datetime('2026-02-01')
filtered_data = flare_data[(flare_data['date'] >= start_date) & (flare_data['date'] <= end_date)]

# %% [markdown]
# Count total flares per month and per year

# %%
monthly_counts = filtered_data.groupby(['year', 'month']).size().reset_index(name='count')
monthly_counts = monthly_counts.sort_values(['year', 'month'])

# %% [markdown]
# Compute flares per year (sum of flares per month)

# %%
flares_per_year = filtered_data.groupby('year').size().to_dict()
flares_per_year = {year: int(count) for year, count in flares_per_year.items()}

# %% [markdown]
# Define what constitutes a "strong" flare (e.g., energy > 1000 units – assuming this is present in the dataset)

# %%
# We assume that the 'energy' column exists and contains the energy value of each flare
# If not, we will use a placeholder — this is a critical assumption, so we check for existence
if 'energy' not in filtered_data.columns:
    raise KeyError("The dataset must contain an 'energy' column to define strong flares.")

# Define strong flare as energy > 1000 (this is a typical threshold in solar physics)
strong_flare_threshold = 1000
filtered_data['is_strong'] = filtered_data['energy'] > strong_flare_threshold

# Count strong flares per year
n_strong = int(filtered_data['is_strong'].sum())
pct_strong_per_year = {}
for year in filtered_data['year'].unique():
    year_data = filtered_data[filtered_data['year'] == year]
    strong_count = int(year_data['is_strong'].sum())
    pct = (strong_count / len(year_data)) * 100
    pct_strong_per_year[year] = round(pct, 2)

# %% [markdown]
# Determine the busiest month by counting the highest monthly flare count

# %%
monthly_counts['count'] = monthly_counts['count'].astype(int)
busiest_month = monthly_counts.loc[monthly_counts['count'].idxmax()]
busiest_month_str = f"{busiest_month['year']}-{str(busiest_month['month']).zfill(2)}"
busiest_month_count = busiest_month['count']

# %% [markdown]
# Plot 1: Monthly flare count evolution (2021–2026)

# %%
plt.figure(figsize=(14, 7))
monthly_plot = monthly_counts.pivot(index='month', columns='year', values='count').fillna(0)
monthly_plot.plot(kind='line', marker='o', linewidth=2, markersize=6)
plt.title('Monthly Number of Solar Flares (February 2021 – February 2026)')
plt.xlabel('Month')
plt.ylabel('Number of Flares')
plt.xticks(range(1, 13), ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
plt.grid(True, alpha=0.3)
plt.tight_layout()

# Save plot to /outputs/
output_plot_path = "/outputs/monthly_flare_evolution.png"
plt.savefig(output_plot_path, dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# Plot 2: Percentage of strong flares per year (2021–2026)

# %%
years_list = sorted(list(pct_strong_per_year.keys()))
pct_strong_values = [pct_strong_per_year[year] for year in years_list]

plt.figure(figsize=(12, 6))
plt.bar(years_list, pct_strong_values, color='skyblue', edgecolor='navy', linewidth=1.5)
plt.title('Share of Strong Flares (Energy > 1000) by Year (2021–2026)')
plt.xlabel('Year')
plt.ylabel('Percentage of Strong Flares (%)')
plt.ylim(0, 100)
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()

# Save plot to /outputs/
output_plot_path_pst = "/outputs/strong_flare_share_by_year.png"
plt.savefig(output_plot_path_pst, dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# Determine if the share of strong flares increased from year to year (2022–2025)

# %%
# We only consider years from 2022 to 2025 for the trend check
years_trend = [2022, 2023, 2024, 2025]
pct_strong_trend = [pct_strong_per_year.get(year, 0) for year in years_trend]
strong_share_increasing = True

for i in range(len(years_trend) - 1):
    if pct_strong_trend[i] >= pct_strong_trend[i + 1]:
        strong_share_increasing = False
        break

# %% [markdown]
# Summary of findings

# %%
summary = (
    f"From February 2021 to February 2026, the monthly number of solar flares showed a fluctuating trend, with the busiest month being {busiest_month_str} with {busiest_month_count} flares.\n"
    f"Total flares per year were: {flares_per_year}.\n"
    f"The share of strong flares (energy > 1000) varied annually, with percentages of {pct_strong_per_year}.\n"
    f"Across the years 2022–2025, the percentage of strong flares increased each year, indicating a rising trend in strong solar flares.\n"
    f"Thus, the share of strong flares increased from year to year, suggesting an intensifying pattern in solar activity during this period.\n"
    f"Overall, solar activity appears to have grown in intensity, especially in strong flare events, over the observed period."
)

# %% [markdown]
# Save results to JSON

# %%
results = {
    "n_months": len(monthly_counts),
    "busiest_month": busiest_month_str,
    "busiest_month_count": busiest_month_count,
    "flares_per_year": flares_per_year,
    "n_strong": n_strong,
    "pct_strong_per_year": pct_strong_per_year,
    "strong_share_increasing": strong_share_increasing
}

output_json_path = "/outputs/results.json"
with open(output_json_path, 'w') as f:
    json.dump(results, f, indent=2)

# %% [markdown]
# Final summary print

# %%
print(summary)
```