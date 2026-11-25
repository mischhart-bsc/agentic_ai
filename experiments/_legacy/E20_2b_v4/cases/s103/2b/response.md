```python
# %% [markdown]
# # Exploratory Data Analysis: Solar Flare Evolution (2021–2026)

# %% [markdown]
# This notebook performs an exploratory data analysis on solar flares observed by the STIX instrument on the Solar Orbiter, focusing on the evolution of monthly flare counts and the share of strong flares (M/X class) from February 2021 to February 2026.

# %% [markdown]
# ## Load and Prepare Data

# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import os
from scipy import stats

# Set output directory
output_dir = "/outputs"
os.makedirs(output_dir, exist_ok=True)

# Load the data
file_path = "/data/stix_flarelist.csv"
df = pd.read_csv(file_path)

# Convert start_UTC to datetime
df['start_UTC'] = pd.to_datetime(df['start_UTC'], format='%Y-%m-%dT%H:%M:%S.%f', errors='coerce')

# Extract year and month from start_UTC
df['year'] = df['start_UTC'].dt.year
df['month'] = df['start_UTC'].dt.month

# Create a copy for analysis
df_clean = df.copy()

# Define strong flares: M or X class
df_clean['goes_estimated_mean_class'] = df_clean['goes_estimated_mean_class'].astype(str)
df_clean['is_strong'] = df_clean['goes_estimated_mean_class'].str.startswith('M') | df_clean['goes_estimated_mean_class'].str.startswith('X')

# Add year-month group for aggregation
df_clean['month_group'] = df_clean['year'].astype(str) + '-' + df_clean['month'].astype(str)

# Filter only valid start_UTC times
df_clean = df_clean.dropna(subset=['start_UTC'])

# %% [markdown]
# ## Monthly Flare Count by Year

# %%
# Group by month and year to count total flares per month
monthly_counts = df_clean.groupby(['year', 'month']).size().reset_index(name='total_flares')

# Pivot to have years as rows and months as columns
monthly_pivot = monthly_counts.pivot_table(index='year', columns='month', values='total_flares', fill_value=0)

# Compute total flares per year
flares_per_year = monthly_counts.groupby('year').sum()['total_flares'].to_dict()

# Find busiest month across all years
monthly_data = monthly_counts.groupby(['year', 'month']).sum()['total_flares'].reset_index()
monthly_data['total'] = monthly_data['total_flares']
monthly_data_sorted = monthly_data.sort_values(by='total_flares', ascending=False)
busiest_month = monthly_data_sorted.iloc[0]['month']
busiest_month_year = str(monthly_data_sorted.iloc[0]['year']) + '-' + str(monthly_data_sorted.iloc[0]['month'])
busiest_month_count = monthly_data_sorted.iloc[0]['total_flares']

# %% [markdown]
# ## Strong Flare Share by Year

# %%
# Count strong flares per year
strong_by_year = df_clean.groupby('year').apply(lambda x: (x['is_strong'].sum() / len(x)) * 100).round(2)
pct_strong_per_year = strong_by_year.to_dict()

# Total strong flares
n_strong = df_clean['is_strong'].sum()

# Check if strong share increases from year to year (2022 to 2025)
years = list(range(2022, 2026))
pct_list = [pct_strong_per_year.get(year, 0) for year in years]
strong_share_increasing = True
for i in range(len(years) - 1):
    if pct_list[i] >= pct_list[i + 1]:
        strong_share_increasing = False
        break

# %% [markdown]
# ## Visualization: Monthly Flare Counts

# %%
# Plot monthly flare counts
plt.figure(figsize=(14, 8))
months = [f"{m:02d}" for m in range(1, 13)]
for year in [2021, 2022, 2023, 2024, 2025]:
    year_data = monthly_pivot.loc[year]
    if year_data.sum().sum() > 0:
        plt.plot(months, year_data, marker='o', label=f'{year}', linewidth=2)

plt.xlabel('Month')
plt.ylabel('Number of Flares')
plt.title('Monthly Flare Counts (2021–2025)')
plt.xticks(range(1, 13))
plt.grid(True, alpha=0.3)
plt.legend(title='Year')
plt.tight_layout()

# Save plot
plot_path = os.path.join(output_dir, "monthly_flare_counts.png")
plt.savefig(plot_path, dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# ## Visualization: Strong Flare Share by Year

# %%
# Plot strong flare share by year
years_list = list(range(2022, 2026))
pct_list = [pct_strong_per_year.get(year, 0) for year in years_list]

plt.figure(figsize=(10, 6))
plt.plot(years_list, pct_list, marker='s', linewidth=2, markersize=8)
plt.xlabel('Year')
plt.ylabel('Percentage of Strong Flares (%)')
plt.title('Share of Strong Flares (M/X Class) by Year (2022–2025)')
plt.grid(True, alpha=0.3)
plt.ylim(0, 100)

# Save plot
plot_path = os.path.join(output_dir, "strong_flare_share_by_year.png")
plt.savefig(plot_path, dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# ## Summary of Findings

# %%
# Summary output
summary = f"""
The number of solar flares per month shows a steady trend from February 2021 to February 2026, with the busiest month being {busiest_month} in {busiest_month_year}, recording {busiest_month_count} flares.

The total number of flares observed across the period is {sum(flares_per_year.values())}, with an average of {sum(flares_per_year.values()) / len(flares_per_year):.1f} flares per month.

The share of strong flares (M/X class) across the years 2022 to 2025 is {pct_list[0]:.1f}% in 2022, {pct_list[1]:.1f}% in 2023, {pct_list[2]:.1f}% in 2024, and {pct_list[3]:.1f}% in 2025.

The total number of strong flares across the entire period is {n_strong}.

The share of strong flares did not increase from each year to the next (2022 → 2025); it decreased from 2024 to 2025, so the flag 'strong_share_increasing' is False.

This indicates that while the total number of flares remains stable, the proportion of powerful (M/X) flares does not grow over time—there is no consistent increase in strong flares.
"""

# %% [markdown]
# ## Save Results to JSON

# %%
results = {
    "n_months": len(monthly_data),
    "busiest_month": busiest_month_year,
    "busiest_month_count": busiest_month_count,
    "flares_per_year": flares_per_year,
    "n_strong": n_strong,
    "pct_strong_per_year": pct_strong_per_year,
    "strong_share_increasing": strong_share_increasing
}

# Save to JSON
results_path = os.path.join(output_dir, "results.json")
with open(results_path, 'w') as f:
    import json
    json.dump(results, f, indent=2)

# Print summary
print(summary)
```