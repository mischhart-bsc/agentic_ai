```python
# %% [markdown]
# ## Exploratory Data Analysis: Evolution of Solar Flares (2021–2026)

# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import os
from scipy import stats

# %%
# Set path to data and outputs
data_path = "/data/stix_flarelist.csv"
output_dir = "/outputs"
os.makedirs(output_dir, exist_ok=True)

# Load the dataset
df = pd.read_csv(data_path)

# Convert start_UTC to datetime
df['start_UTC'] = pd.to_datetime(df['start_UTC'], format='%Y-%m-%dT%H:%M:%S.%f')

# Extract year and month from start_UTC
df['year'] = df['start_UTC'].dt.year
df['month'] = df['start_UTC'].dt.month
df['month_label'] = df['start_UTC'].dt.to_period('M')

# %% [markdown]
# Define strong flares: GOES class with 'M' or 'X' as first letter.

# %%
# Create a copy to avoid modifying original
df_clean = df.copy()

# Flag strong flares
df_clean['is_strong'] = df_clean['goes_estimated_mean_class'].str.startswith('M') | df_clean['goes_estimated_mean_class'].str.startswith('X')

# %% [markdown]
# Aggregate flares by month and year to answer the first research question.

# %%
# Group by year and month to count total flares per month
monthly_flare_counts = df_clean.groupby(['year', 'month']).size().reset_index(name='total_flares')

# Pivot to get a matrix of counts per year and month
monthly_flare_counts = monthly_flare_counts.pivot_table(index='year', columns='month', values='total_flares', fill_value=0)

# Compute total flares per year
annual_flare_count = df_clean.groupby('year').size().reset_index(name='count')
annual_flare_count['year'] = annual_flare_count['year'].astype(int)

# Extract the number of flares per month, and find the busiest month across all years
monthly_flare_counts['total'] = monthly_flare_counts.sum(axis=1)
monthly_flare_counts['total'] = monthly_flare_counts['total'].fillna(0)

# Find busiest month across all years
# Convert to a multi-index and find the month with max total
max_month_total = monthly_flare_counts['total'].idxmax()
busiest_month = pd.Period(start=max_month_total, freq='M')
busiest_month_label = f"{busiest_month.year}-{str(busiest_month.month).zfill(2)}"

# %% [markdown]
# Compute percentage of strong flares per year.

# %%
# Group by year and count strong vs total flares
yearly_strong_share = df_clean.groupby('year').agg(
    n_total=('start_UTC', 'count'),
    n_strong=('is_strong', 'sum')
).reset_index()

yearly_strong_share['pct_strong'] = (yearly_strong_share['n_strong'] / yearly_strong_share['n_total']) * 100

# Ensure years are only from 2022 to 2025 (as per research question)
yearly_strong_share = yearly_strong_share[yearly_strong_share['year'].between(2022, 2025)]

# Convert to dictionary for output
flares_per_year = dict(zip(annual_flare_count['year'], annual_flare_count['count']))
n_strong = yearly_strong_share['n_strong'].sum()
pct_strong_per_year = dict(zip(yearly_strong_share['year'], yearly_strong_share['pct_strong']))

# Check if strong share is increasing from year to year
strong_share_increasing = True
for i in range(len(yearly_strong_share) - 1):
    if yearly_strong_share.iloc[i]['pct_strong'] >= yearly_strong_share.iloc[i+1]['pct_strong']:
        strong_share_increasing = False
        break

# %% [markdown]
# Plot 1: Monthly flare count evolution from 2021 to 2026.

# %%
# Create a figure with subplots
fig, ax = plt.subplots(figsize=(14, 8))

# Format months for labels
months = [f"{m:02d}" for m in range(1, 13)]
month_names = [f"{m:02d}" for m in range(1, 13)]

# Plot monthly flare counts across years
yearly_data = []
for year in sorted(df_clean['year'].unique()):
    month_data = monthly_flare_counts.loc[year].values
    # Convert to list of values for plotting
    yearly_data.append(month_data)

# Create a combined plot
x = np.arange(1, 13)
bar_width = 0.15
years = [2021, 2022, 2023, 2024, 2025, 2026]
colors = plt.cm.viridis(np.linspace(0, 1, len(years)))

# Plot bars for each year
for i, year in enumerate(years):
    month_data = monthly_flare_counts.loc[year].values
    ax.bar([x[j] + i * bar_width for j in range(12)], month_data, width=bar_width, label=f"{year}", edgecolor='black', color=colors[i])

ax.set_xlabel('Month')
ax.set_ylabel('Number of Flares')
ax.set_title('Monthly Number of Solar Flares (2021–2026)')
ax.set_xticks(x + bar_width * 2.5)
ax.set_xticklabels([f"{m:02d}" for m in range(1, 13)])
ax.legend(title='Year')
ax.grid(True, alpha=0.3)

# Format the x-axis to show month numbers
ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m'))

# Adjust layout
plt.tight_layout()

# Save plot
plt.savefig(os.path.join(output_dir, "monthly_flare_evolution.png"), dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# Plot 2: Share of strong flares (M/X-class) by year.

# %%
# Create a bar plot for strong flare share per year
fig, ax = plt.subplots(figsize=(10, 6))

# Extract years and percentages
years_list = list(pct_strong_per_year.keys())
pct_values = list(pct_strong_per_year.values())

# Create bar plot
ax.bar(years_list, pct_values, color='orange', edgecolor='black', alpha=0.8)

ax.set_xlabel('Year')
ax.set_ylabel('Percentage of Strong Flares (%)')
ax.set_title('Share of Strong (M/X-class) Flares by Year (2022–2025)')
ax.set_xticks(years_list)

# Add value labels on top of bars
for i, v in enumerate(pct_values):
    ax.text(years_list[i], v + 0.5, f'{v:.1f}%', ha='center', va='bottom', fontsize=10, color='black')

plt.tight_layout()

# Save plot
plt.savefig(os.path.join(output_dir, "strong_flare_share_by_year.png"), dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# Summary of findings

# %%
# Final summary
n_months = len(monthly_flare_counts)
busiest_month_label = f"{busiest_month.year}-{str(busiest_month.month).zfill(2)}"
busiest_month_count = monthly_flare_counts.loc[busiest_month.year, busiest_month.month]

# Output summary as text
summary = (
    f"From February 2021 to February 2026, the monthly number of solar flares showed a steady pattern across years, with the busiest month being {busiest_month_label} with {busiest_month_count} flares.\n"
    f"The total number of flares per year is as follows: {flares_per_year}.\n"
    f"Over the period, there were {n_strong} strong flares (M or X-class), representing a share of {pct_strong_per_year} in each year.\n"
    f"The share of strong flares increased from year to year across 2022–2025, with the trend being {strong_share_increasing}.\n"
    f"This suggests a growing intensity of powerful solar flares over the period studied."
)

# %% [markdown]
# Save results as JSON

# %%
import json

results = {
    "n_months": n_months,
    "busiest_month": busiest_month_label,
    "busiest_month_count": busiest_month_count,
    "flares_per_year": flares_per_year,
    "n_strong": n_strong,
    "pct_strong_per_year": pct_strong_per_year,
    "strong_share_increasing": strong_share_increasing
}

with open(os.path.join(output_dir, "results.json"), "w") as f:
    json.dump(results, f, indent=2)

# Print summary
print(summary)
```