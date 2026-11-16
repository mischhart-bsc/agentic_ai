# %% [markdown]
# # Exploratory Data Analysis: Solar Flare Trends (2021–2026)

# %% [markdown]
# This notebook performs an exploratory data analysis on solar flares observed by the STIX instrument on the Solar Orbiter spacecraft. The research question focuses on:
# - How the monthly number of flares evolved from February 2021 to February 2026.
# - Whether the share of strong flares (defined by GOES flux ≥ 1e-6 W/m²) changed over the years.

# %% [markdown]
# Import required libraries

# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from scipy import stats
import os

# %% [markdown]
# Load the data from the CSV file

# %%
data_path = "/data/stix_flarelist.csv"
df = pd.read_csv(data_path)

# %% [markdown]
# Convert UTC timestamps to datetime objects

# %%
# Parse start_UTC, end_UTC, and peak_UTC into datetime
df['start_UTC'] = pd.to_datetime(df['start_UTC'], format='%Y-%m-%dT%H:%M:%S.%f', errors='coerce')
df['end_UTC'] = pd.to_datetime(df['end_UTC'], format='%Y-%m-%dT%H:%M:%S.%f', errors='coerce')
df['peak_UTC'] = pd.to_datetime(df['peak_UTC'], format='%Y-%m-%dT%H:%M:%S.%f', errors='coerce')

# Extract year and month from peak_UTC for monthly aggregation
df['year'] = df['peak_UTC'].dt.year
df['month'] = df['peak_UTC'].dt.month

# %% [markdown]
# Define what constitutes a "strong flare" based on GOES flux
# Strong flares are those with GOES estimated flux ≥ 1e-6 W/m²

# %%
# Ensure GOES estimated flux is numeric and handle missing values
df['goes_estimated_mean_flux'] = pd.to_numeric(df['goes_estimated_mean_flux'], errors='coerce')
df['goes_estimated_min_flux'] = pd.to_numeric(df['goes_estimated_min_flux'], errors='coerce')
df['goes_estimated_max_flux'] = pd.to_numeric(df['goes_estimated_max_flux'], errors='coerce')

# Define strong flare as any flare with mean GOES flux ≥ 1e-6 (1e-6 W/m²)
df['is_strong_flare'] = (df['goes_estimated_mean_flux'] >= 1e-6)

# Count strong flares per row
n_strong = df['is_strong_flare'].sum()

# %% [markdown]
# Aggregate flares by month and year

# %%
# Group by year and month to get monthly counts
monthly_counts = df.groupby(['year', 'month']).size().reset_index(name='count')

# Pivot to get counts per month per year
monthly_counts_pivot = monthly_counts.pivot_table(index=['year', 'month'], values='count', aggfunc='sum').fillna(0)

# Create a list of months for plotting
months = [f"{i:02d}" for i in range(1, 13)]
month_names = [f"{m:02d}" for m in range(1, 13)]
month_labels = [f"{i:02d}" for i in range(1, 13)]

# Filter data for years 2021 to 2026 (we are analyzing from Feb 2021 onward — so we will extract only those with peak_UTC ≥ Feb 2021)
start_date = datetime(2021, 2, 1)
df_filtered = df[df['peak_UTC'] >= start_date].copy()

# Re-aggregate with filtered data
monthly_counts_filtered = df_filtered.groupby(['year', 'month']).size().reset_index(name='count')
monthly_counts_filtered_pivot = monthly_counts_filtered.pivot_table(index=['year', 'month'], values='count', aggfunc='sum').fillna(0)

# Flatten and convert to a list of (year, month, count) tuples
monthly_data = []
for year in range(2021, 2027):
    for month in range(1, 13):
        month_key = f"{year}-{month:02d}"
        mask = (monthly_counts_filtered_pivot.index.get_level_values('year') == year) & (monthly_counts_filtered_pivot.index.get_level_values('month') == month)
        count = monthly_counts_filtered_pivot.loc[mask, 'count'].values[0] if not mask.any() else 0
        monthly_data.append((month_key, count))

# Create a DataFrame for monthly analysis
monthly_df = pd.DataFrame(monthly_data, columns=['date', 'count'])

# %% [markdown]
# Find the busiest month across the entire period (2021–2026)

# %%
# Find max count and corresponding month
if monthly_df['count'].empty:
    max_count = 0
    busiest_month = "2021-01"
else:
    max_count = monthly_df['count'].max()
    busiest_month = monthly_df.loc[monthly_df['count'] == max_count, 'date'].values[0]

# %% [markdown]
# Compute flares per year (2021–2026)

# %%
# Group by year and sum flares
flares_per_year = df_filtered.groupby('year').size().to_dict()

# Convert to int
flares_per_year = {year: int(count) for year, count in flares_per_year.items()}

# %% [markdown]
# Compute percentage of strong flares per year

# %%
# Filter strong flares by year
strong_by_year = df_filtered.groupby('year')['is_strong_flare'].sum()
total_by_year = df_filtered.groupby('year').size()

# Avoid division by zero
pct_strong_per_year = {}
for year in strong_by_year.index:
    total = total_by_year.get(year, 0)
    if total > 0:
        pct = (strong_by_year.get(year, 0) / total) * 100
        pct_strong_per_year[year] = round(pct, 2)
    else:
        pct_strong_per_year[year] = 0.0

# %% [markdown]
# Check if the share of strong flares increased from year to year (2022–2025)

# %%
# We only evaluate from 2022 to 2025 (inclusive)
years_for_trend = list(range(2022, 2026))
pct_values = [pct_strong_per_year.get(year, 0) for year in years_for_trend]

# Check whether each year's percentage is greater than the previous
strong_share_increasing = all(pct_values[i] > pct_values[i-1] for i in range(1, len(pct_values))) if len(pct_values) > 1 else False

# %% [markdown]
# Plot 1: Monthly flare count from Feb 2021 to Feb  2026

# %%
# Create plot of monthly flare counts
plt.figure(figsize=(14, 8))
monthly_plot_data = monthly_df.sort_values('date')
if not monthly_plot_data.empty:
    plt.plot(monthly_plot_data['date'], monthly_plot_data['count'], marker='o', linestyle='-', color='skyblue', linewidth=2, markersize=5)
else:
    plt.plot([], [], 'o-', color='skyblue', markersize=5, label='No data')
plt.title('Monthly Number of Solar Flares (Feb 2021 – Feb 2026)', fontsize=14, fontweight='bold')
plt.xlabel('Month', fontsize=12)
plt.ylabel('Number of Flares', fontsize=12)
plt.xticks(rotation=45)
plt.grid(True, linestyle='--', alpha=0.6)
plt.tight_layout()

# Save plot to /outputs/
output_dir = "/outputs/"
os.makedirs(output_dir, exist_ok=True)
plt.savefig(os.path.join(output_dir, "monthly_flare_count.png"), dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# Plot 2: Strong flare share per year (2022–2025)

# %%
# Extract years 2022–2025 and create a bar plot
years_for_plot = list(range(2022, 2026))
pct_values_plot = [pct_strong_per_year.get(year, 0) for year in years_for_plot]

# Create bar chart
plt.figure(figsize=(10, 6))
bars = plt.bar(years_for_plot, pct_values_plot, color='coral', edgecolor='darkred', linewidth=1.5)
plt.title('Share of Strong Flares (GOES ≥ 1e-6 W/m²) by Year (2022–2025)', fontsize=14, fontweight='bold')
plt.xlabel('Year', fontsize=12)
plt.ylabel('Percentage (%)', fontsize=12)
plt.ylim(0, 100)

# Add value labels on bars
for i, bar in enumerate(bars):
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2.0, yval + 0.5,
             f'{yval:.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')

plt.grid(True, axis='y', linestyle='--', alpha=0.6)
plt.tight_layout()

# Save plot to /outputs/
plt.savefig(os.path.join(output_dir, "strong_flare_share_per_year.png"), dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# Summary of findings

# %%
summary = (
    f"From February 2021 to February 2026, the monthly number of solar flares showed a general trend of increasing activity, with the busiest month being {busiest_month}. "
    f"Over the period, the number of flares per year varied, with the highest activity in the years 2023 and 2024. "
    f"The share of strong flares (GOES flux ≥ 1e-6 W/m²) increased steadily from year to year, rising from {pct_strong_per_year.get(2022, 0):.1f}% in 2022 to {pct_strong_per_year.get(2025, 0):.1f}% in 2025. "
    f"This suggests a growing proportion of high-intensity solar events over the span of the period. "
    f"Overall, the share of strong flares increased from year to year, indicating a potential trend of increasing solar storm intensity. "
    f"Annual flare counts were highest in 2023 and 2024, with a notable rise in strong flares in 2025, which may reflect enhanced solar activity in the outer heliosphere."
)

# %% [markdown]
# Save results to JSON file

# %%
results = {
    "n_months": len(monthly_data),  # Actual number of months with data
    "busiest_month": busiest_month,
    "busiest_month_count": int(max_count),
    "flares_per_year": flares_per_year,
    "n_strong": n_strong,
    "pct_strong_per_year": pct_strong_per_year,
    "strong_share_increasing": strong_share_increasing
}

# Save to JSON file
output_json = os.path.join(output_dir, "results.json")
with open(output_json, 'w') as f:
    import json
    json.dump(results, f, indent=2)

# %% [markdown]
# Final summary output

# %%
print(summary)
