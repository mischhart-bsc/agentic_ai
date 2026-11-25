```python
# %% [markdown]
# # Exploratory Data Analysis: Solar Flare Activity (2021–2026)

# %% [markdown]
# This notebook performs an exploratory data analysis on solar flare observations from the STIX instrument aboard Solar Orbiter. The research question focuses on:
# - How the monthly number of flares evolved from February 2021 to February 2026.
# - Whether the share of strong flares (defined by GOES class B4 or higher) changed over time.

# %% [markdown]
# Import required libraries

# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import scipy.stats as stats
import os

# %% [markdown]
# Load the data from the CSV file

# %%
file_path = "/data/stix_flarelist.csv"
data = pd.read_csv(file_path)

# Convert UTC timestamps to datetime objects
data['start_UTC'] = pd.to_datetime(data['start_UTC'])
data['peak_UTC'] = pd.to_datetime(data['peak_UTC'])
data['end_UTC'] = pd.to_datetime(data['end_UTC'])

# Extract year and month for grouping
data['year_month'] = data['start_UTC'].dt.to_period('M')

# Filter data to include only observations from February 2021 to February 2026
start_date = pd.Timestamp('2021-02-01')
# Use end_date as last day of February in the last year (2026)
end_date = pd.Timestamp('2026-02-28')  # February has 28 days in 2026
filtered_data = data[(data['start_UTC'] >= start_date) & (data['start_UTC'] <= end_date)]

# Define "strong flare" as GOES class B4 or higher
filtered_data['strong_flare'] = filtered_data['goes_estimated_min_class'].str.contains('B4|C|M|X', case=False, na=False)

# Create a summary of strong flares
strong_flare_mask = filtered_data['strong_flare']

# %% [markdown]
# Count flares by month and year

# %%
monthly_counts = filtered_data.groupby('year_month').size().reset_index(name='count')
monthly_counts['year_month'] = monthly_counts['year_month'].astype(str)

# %% [markdown]
# Generate a line plot of monthly flare counts

# %%
plt.figure(figsize=(14, 8))
monthly_counts_plot = monthly_counts.copy()
monthly_counts_plot['year_month'] = pd.to_datetime(monthly_counts_plot['year_month'])

plt.plot(monthly_counts_plot['year_month'], monthly_counts_plot['count'], marker='o', linewidth=2, markersize=6)
plt.title('Monthly Solar Flare Count (Feb 2021 – Feb 2026)', fontsize=16, pad=20)
plt.xlabel('Month', fontsize=12)
plt.ylabel('Number of Flares', fontsize=12)
plt.xticks(rotation=45)
plt.grid(True, alpha=0.3)
plt.tight_layout()

# Save plot to outputs/
output_dir = "/outputs/"
os.makedirs(output_dir, exist_ok=True)
plt.savefig(os.path.join(output_dir, "monthly_flare_count.png"))
plt.close()

# %% [markdown]
# Compute cumulative flare count by year and identify busiest month

# %%
# Extract year from year_month and group by year
yearly_counts = filtered_data.groupby(filtered_data['start_UTC'].dt.year).size().reset_index(name='count')
yearly_counts['year'] = yearly_counts['start_UTC'].astype(int)

# Compute total flares per year
flares_per_year = yearly_counts.set_index('year')['count'].to_dict()

# Find busiest month across the period
busiest_month_data = monthly_counts.loc[monthly_counts['count'].idxmax()]
busiest_month = busiest_month_data['year_month'].strftime('%Y-%m')
busiest_month_count = busiest_month_data['count']

# %% [markdown]
# Compute share of strong flares per year

# %%
# Calculate strong flare count per year
strong_per_year = filtered_data.groupby(filtered_data['start_UTC'].dt.year).apply(
    lambda x: (x['strong_flare'].sum() / len(x)) * 100).round(2)

# Convert to dictionary
pct_strong_per_year = strong_per_year.to_dict()

# Check if share of strong flares increases from year to year (2022–2025)
years = list(range(2022, 2026))
pct_strong_values = [pct_strong_per_year.get(year, 0) for year in years]
strong_share_increasing = True

for i in range(len(years) - 1):
    if pct_strong_values[i] >= pct_strong_values[i + 1]:
        strong_share_increasing = False
        break

# %% [markdown]
# Summary of findings

# %%
n_months = len(monthly_counts)
n_strong = strong_flare_mask.sum()
flares_per_year_dict = {year: count for year, count in flares_per_year.items()}

# %% [markdown]
# Save results in JSON

# %%
results = {
    "n_months": n_months,
    "busiest_month": busiest_month,
    "busiest_month_count": busiest_month_count,
    "flares_per_year": flares_per_year_dict,
    "n_strong": n_strong,
    "pct_strong_per_year": pct_strong_per_year,
    "strong_share_increasing": strong_share_increasing
}

output_json_path = os.path.join(output_dir, "results.json")
with open(output_json_path, 'w') as f:
    import json
    json.dump(results, f, indent=2)

# %% [markdown]
# Final Summary

# %%
print(f"Over the period from February 2021 to February 2026, there were {n_months} months of solar flare observations.")
print(f"The busiest month was {busiest_month} with {busiest_month_count} flares.")
print(f"Total flares per year: {flares_per_year_dict}")
print(f"Number of strong flares (GOES B4+): {n_strong}")
print(f"Percentage of strong flares per year: {pct_strong_per_year}")
print(f"The share of strong flares increased from year to year from 2022 to 2025: {strong_share_increasing}")
```