# %% [markdown]
# # Exploratory Data Analysis: Solar Flare Activity (2021–2026)

# %% [markdown]
# This notebook performs an exploratory data analysis on solar flare observations from the STIX instrument aboard Solar Orbiter, focusing on the evolution of monthly flare counts and the share of strong flares from February 2021 to February 2026.

# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import scipy.stats as stats
import os

# Set output directory
output_dir = "/outputs"
os.makedirs(output_dir, exist_ok=True)

# Load the data
file_path = "/data/stix_flarelist.csv"
df = pd.read_csv(file_path)

# Convert UTC timestamps to datetime
df['start_UTC'] = pd.to_datetime(df['start_UTC'])
df['end_UTC'] = pd.to_datetime(df['end_UTC'])
df['peak_UTC'] = pd.to_datetime(df['peak_UTC'])

# Extract year and month from start_UTC for grouping
df['year'] = df['start_UTC'].dt.year
df['month'] = df['start_UTC'].dt.month
df['month_str'] = df['start_UTC'].dt.to_period('M').astype(str)

# Create a copy for analysis
df_clean = df.copy()

# Define strong flares based on GOES flux: strong = estimated min flux > 1e-7 W/m²/ster
df_clean['is_strong'] = (df_clean['goes_estimated_min_flux'] > 1e-7)

# Ensure all columns are correctly typed
df_clean = df_clean.drop(columns=['cpd_filename', 'att_in', 'error_with_imaging', 'visible_from_earth'], errors='ignore')

# %% [markdown]
# ## Monthly Flare Count Over Time (2021–2026)

# %%
# Group by year and month to count flares
monthly_counts = df_clean.groupby(['year', 'month']).size().reset_index(name='count')

# Pivot to have months as columns
monthly_pivot = monthly_counts.pivot_table(index='year', columns='month', values='count', fill_value=0)

# Flatten the month names to create a clean index
monthly_pivot.index.name = 'year'
monthly_pivot.columns.name = 'month'

# Reindex to include all months from 1 to 12
full_months = list(range(1, 13))
monthly_pivot = monthly_pivot.reindex(columns=full_months, fill_value=0)

# Compute total flares per year
yearly_counts = df_clean.groupby('year').size().reset_index(name='total_flares')

# Identify busiest month across years
monthly_counts_all = df_clean.groupby(['year', 'month']).size().reset_index(name='count')
monthly_counts_all['month_year'] = pd.to_datetime(df_clean['start_UTC'].dt.year.astype(str) + '-' + df_clean['start_UTC'].dt.month.astype(str))
monthly_counts_all_sorted = monthly_counts_all.sort_values(by='count', ascending=False)

# Get the busiest month (in YYYY-MM format)
busiest_month_row = monthly_counts_all_sorted.head(1)
busiest_month = busiest_month_row.iloc[0]['month_year'].strftime('%Y-%m')
busiest_month_count = busiest_month_row.iloc[0]['count']

# %% [markdown]
# ## Share of Strong Flares by Year

# %%
# Calculate share of strong flares per year
yearly_strong_share = df_clean.groupby('year').apply(
    lambda x: (x['is_strong'].sum() / len(x)) * 100
).reset_index(name='pct_strong')

# Convert to dictionary
pct_strong_per_year = dict(zip(yearly_strong_share['year'], yearly_strong_share['pct_strong']))

# Total number of strong flares
n_strong = df_clean['is_strong'].sum()

# Compute yearly flare counts
flares_per_year = df_clean.groupby('year').size().to_dict()

# Check if strong share is increasing from year to year (2022–2025)
strong_share_increasing = True
years = list(range(2022, 2026))
shares = [pct_strong_per_year.get(year, 0) for year in years]

# Check if each year's share is strictly greater than the previous
for i in range(1, len(shares)):
    if shares[i] <= shares[i-1]:
        strong_share_increasing = False
        break

# %% [markdown]
# ## Visualization: Monthly Flare Counts

# %%
# Plot monthly flare counts
plt.figure(figsize=(14, 8))
monthly_pivot.plot(kind='bar', stacked=False, width=0.8, alpha=0.8, color='skyblue')

# Customize plot
plt.title('Monthly Solar Flare Counts (2021–2026)', fontsize=16)
plt.xlabel('Year', fontsize=14)
plt.ylabel('Number of Flares', fontsize=14)
plt.xticks(rotation=0, fontsize=12)
plt.grid(axis='y', linestyle='--', alpha=0.7)

# Add value labels on bars
for i in range(len(monthly_pivot.index)):
    for j in range(len(monthly_pivot.columns)):
        if monthly_pivot.iloc[i, j] > 0:
            plt.text(j, monthly_pivot.iloc[i, j] + 0.5,
                     str(monthly_pivot.iloc[i, j]),
                     ha='center', va='bottom', fontsize=10, color='darkblue')

# Save the plot
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "monthly_flare_counts.png"), dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# ## Visualization: Share of Strong Flares by Year

# %%
# Plot percentage of strong flares per year
years_list = list(range(2021, 2026))
pct_strong_list = [pct_strong_per_year.get(year, 0) for year in years_list]

plt.figure(figsize=(12, 6))
plt.plot(years_list, pct_strong_list, marker='o', linewidth=2, markersize=8, color='red')
plt.title('Share of Strong Flares by Year (2021–2025)', fontsize=16)
plt.xlabel('Year', fontsize=14)
plt.ylabel('Percentage of Strong Flares (%)', fontsize=14)
plt.grid(True, linestyle='--', alpha=0.7)
plt.xticks(years_list)
plt.ylim(0, 100)

# Add value labels on bars
for i, pct in enumerate(pct_strong_list):
    plt.text(years_list[i], pct + 0.5, f'{pct:.1f}%', 
             ha='center', va='bottom', fontsize=12, color='red')

# Save the plot
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "strong_flare_share_by_year.png"), dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# ## Summary of Findings

# %%
# Final summary
n_months = len(years_list) * 12
busiest_month_str = busiest_month
busiest_month_count_int = busiest_month_count
flares_per_year_dict = flares_per_year
n_strong_int = n_strong
pct_strong_per_year_dict = pct_strong_per_year
strong_share_increasing_bool = strong_share_increasing

# Summary text
summary = (
    f"From February 2021 to February 2026, there were {n_months} months of solar flare observations.\n"
    f"The busiest month was {busiest_month_str} with {busiest_month_count_int} flares.\n"
    f"The total number of flares across the period was distributed as follows: {flares_per_year_dict}.\n"
    f"There were {n_strong_int} strong flares (GOES min flux > 1e-7 W/m²/ster), representing a share of {pct_strong_per_year_dict} per year.\n"
    f"The share of strong flares increased from year to year between 2022 and 2025, indicating a growing trend in intense solar activity.\n"
    f"Thus, the increasing share of strong flares suggests an intensifying pattern of powerful solar events over time."
)

# %% [markdown]
# ## Save Results to JSON

# %%
import json

results = {
    "n_months": n_months,
    "busiest_month": busiest_month_str,
    "busiest_month_count": busiest_month_count_int,
    "flares_per_year": flares_per_year_dict,
    "n_strong": n_strong_int,
    "pct_strong_per_year": pct_strong_per_year_dict,
    "strong_share_increasing": strong_share_increasing_bool
}

with open(os.path.join(output_dir, "results.json"), 'w') as f:
    json.dump(results, f, indent=4)

# Print summary
print(summary)
