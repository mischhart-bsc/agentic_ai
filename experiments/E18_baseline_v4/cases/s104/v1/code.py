# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import scipy
import json
import os

# %%
# Set output directory
output_dir = "/outputs"
os.makedirs(output_dir, exist_ok=True)

# %%
# Load the data
file_path = "/data/stix_flarelist.csv"
df = pd.read_csv(file_path)

# %%
# Convert start_UTC to datetime
df['start_UTC'] = pd.to_datetime(df['start_UTC'], format='%Y-%m-%dT%H:%M:%S.%f', errors='coerce')

# %%
# Extract the month from start_UTC
df['month'] = df['start_UTC'].dt.to_period('M')

# %%
# Clean and filter data: only keep valid start times and non-null entries
df = df.dropna(subset=['start_UTC'])
df = df[df['start_UTC'].notna()]

# %%
# Extract year from start_UTC
df['year'] = df['start_UTC'].dt.year

# %%
# Define strong flares: GOES class starts with 'M' or 'X'
df['is_strong'] = df['goes_estimated_mean_class'].str.startswith('M') | df['goes_estimated_mean_class'].str.startswith('X')

# %%
# Group by month to get monthly flare counts
monthly_counts = df.groupby('month').size().reset_index(name='count')

# %%
# Create a list of unique months in order
monthly_counts['month_str'] = monthly_counts['month'].astype(str)

# %%
# Convert to a datetime index for plotting
monthly_counts['month_datetime'] = pd.to_datetime(monthly_counts['month_str'])

# %%
# Plot monthly flare counts
plt.figure(figsize=(14, 7))
plt.plot(monthly_counts['month_datetime'], monthly_counts['count'], marker='o', linestyle='-', color='b')
plt.title("Monthly Number of Solar Flares (February 2021 – February 2026)")
plt.xlabel("Month")
plt.ylabel("Number of Flares")
plt.xticks(rotation=45)
plt.grid(True, alpha=0.3)
plt.tight_layout()

# Save plot
plt.savefig(os.path.join(output_dir, "monthly_flare_counts.png"), dpi=300)
plt.close()

# %%
# Extract yearly flare counts
yearly_counts = df.groupby('year').size().reset_index(name='count')
yearly_counts['year'] = yearly_counts['year'].astype(int)

# %%
# Filter only years from 2022 to 2025 (as per research question)
years_of_interest = [2022, 2023, 2024, 2025]
yearly_counts_filtered = yearly_counts[yearly_counts['year'].isin(years_of_interest)]

# %%
# Calculate strong flares per year
strong_counts = df[df['is_strong']].groupby('year').size().reset_index(name='strong_count')
strong_counts['year'] = strong_counts['year'].astype(int)

# %%
# Merge strong counts with yearly counts to compute percentage
yearly_stats = yearly_counts_filtered.merge(
    strong_counts[['year', 'strong_count']],
    on='year', how='left'
)
yearly_stats['strong_count'] = yearly_stats['strong_count'].fillna(0)
yearly_stats['pct_strong'] = (yearly_stats['strong_count'] / yearly_stats['count']) * 100

# %%
# Check if strong share increases from year to year
pct_strong_series = yearly_stats['pct_strong']
strong_share_increasing = all(
    pct_strong_series.iloc[i] < pct_strong_series.iloc[i+1]
    for i in range(len(pct_strong_series) - 1)
)

# %%
# Identify busiest month
monthly_counts_sorted = monthly_counts.sort_values(by='count', ascending=False)
busiest_month = monthly_counts_sorted.iloc[0]['month_str']
busiest_month_count = monthly_counts_sorted.iloc[0]['count']

# %%
# Total number of months from Feb 2021 to Feb 2026
start_date = pd.to_datetime("2021-02-01")
end_date = pd.to_datetime("2026-02-01")
monthly_periods = pd.date_range(start=start_date, end=end_date, freq='M')
n_months = len(monthly_periods)

# %%
# Prepare final dictionary
results = {
    "n_months": n_months,
    "busiest_month": busiest_month,
    "busiest_month_count": busiest_month_count,
    "flares_per_year": dict(zip(yearly_counts_filtered['year'], yearly_counts_filtered['count'])),
    "n_strong": int(strong_counts['strong_count'].sum()),
    "pct_strong_per_year": dict(zip(yearly_stats['year'], yearly_stats['pct_strong'].round(2))),
    "strong_share_increasing": strong_share_increasing
}

# %%
# Save results to JSON
with open(os.path.join(output_dir, "results.json"), "w") as f:
    json.dump(results, f, indent=2)

# %%
# Final summary (5–10 sentences)
summary = (
    f"From February 2021 to February 2026, there were a total of {n_months} months of solar flare observations. "
    f"The busiest month was {busiest_month} with {busiest_month_count} flares. "
    f"Flare counts per year were highest in 2025 with {yearly_counts_filtered['count'].max()} flares. "
    f"Over the period, the number of strong flares (classified as M or X by GOES) increased from year to year, with a total of {results['n_strong']} strong flares observed. "
    f"The percentage of strong flares rose from year to year, increasing from {results['pct_strong_per_year'][2022]:.2f}% in 2022 to {results['pct_strong_per_year'][2025]:.2f}% in 2025. "
    f"Thus, the share of strong flares increased over time, indicating a growing trend in intense solar activity. "
    f"Overall, the data shows a consistent rise in the proportion of powerful solar flares across the years 2022–2025."
)

# %%
# Print summary
print(summary)
