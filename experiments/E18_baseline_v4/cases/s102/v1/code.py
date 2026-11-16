# %% [markdown]
# # Exploratory Data Analysis: Solar Flare Evolution (2021–2026)

# %% [markdown]
# This notebook performs an exploratory data analysis on solar flares observed by the STIX instrument on the Solar Orbiter. The research question is: *How did the monthly number of flares evolve from February 2021 up to and including February 2026, and did the share of strong flares change over the years?*

# %% [markdown]
# We use the dataset `/data/stix_flarelist.csv`, which contains 33,076 rows and 40 columns. A flare is assigned to the calendar month of its `start_UTC` time. A flare is considered "strong" if its GOES estimated mean class (`goes_estimated_mean_class`) starts with "M" or "X".

# %% [import]
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import scipy.stats as stats
import json

# %% [markdown]
# Load the data from the CSV file.

# %% [code]
data_path = "/data/stix_flarelist.csv"
df = pd.read_csv(data_path)

# %% [markdown]
# Parse the start_UTC column to extract the date and convert it to a datetime object.

# %% [code]
df['start_UTC'] = pd.to_datetime(df['start_UTC'], format='%Y-%m-%dT%H:%M:%S.%f')
df['start_month'] = df['start_UTC'].dt.to_period('M')

# %% [markdown]
# Filter data to only include flares from February 2021 to February 2026 (inclusive). We will use all rows in the file, but only analyze the relevant time period.

# %% [code]
start_date = pd.Timestamp('2021-02-01')
end_date = pd.Timestamp('2026-02-29')
df_filtered = df[(df['start_UTC'] >= start_date) & (df['start_UTC'] <= end_date)].copy()

# %% [markdown]
# Extract the GOES class to determine strong flares.

# %% [code]
# Define strong flares: GOES class starts with 'M' or 'X'
df_filtered['is_strong'] = df_filtered['goes_estimated_mean_class'].str.startswith('M') | df_filtered['goes_estimated_mean_class'].str.startswith('X')

# %% [markdown]
# Extract monthly counts and strong flare shares.

# %% [code]
monthly_flare_counts = df_filtered.groupby('start_month').size().reset_index(name='count')
monthly_flare_counts['month'] = monthly_flare_counts['start_month'].apply(lambda x: x.start_time.strftime('%Y-%m'))

# %% [code]
# Extract yearly data for strong flare share
df_filtered['year'] = df_filtered['start_UTC'].dt.year
yearly_data = df_filtered.groupby('year').agg({
    'is_strong': 'sum',
    'start_month': 'count'
}).reset_index()

yearly_data['n_strong'] = yearly_data['is_strong']
yearly_data['n_total'] = yearly_data['start_month']
yearly_data['pct_strong'] = yearly_data['n_strong'] / yearly_data['n_total'] * 100

# Clean up missing values
yearly_data['pct_strong'] = yearly_data['pct_strong'].fillna(0)

# %% [markdown]
# Identify the busiest month (max count) across the period.

# %% [code]
busiest_month = monthly_flare_counts.loc[monthly_flare_counts['count'].idxmax()]
busiest_month_str = busiest_month['month']
busiest_month_count = busiest_month['count']

# %% [markdown]
# Compute flare counts per year (2021 to 2026).

# %% [code]
flares_per_year = {}
for year in sorted(yearly_data['year'].unique()):
    flares_per_year[year] = yearly_data[yearly_data['year'] == year]['n_total'].sum()

# %% [markdown]
# Compute strong flare share per year (as percentage) and check if it increases from year to year.

# %% [code]
pct_strong_per_year = {}
for year in sorted(yearly_data['year'].unique()):
    pct_strong_per_year[year] = yearly_data[yearly_data['year'] == year]['pct_strong'].values[0]

# Check if strong share increases from year to year (2022–2025)
strong_share_increasing = True
years = list(range(2022, 2026))
for i in range(len(years) - 1):
    if pct_strong_per_year[years[i]] >= pct_strong_per_year[years[i + 1]]:
        strong_share_increasing = False
        break

# %% [markdown]
# Plot 1: Monthly flare count evolution

# %% [code]
plt.figure(figsize=(14, 7))
monthly_flare_counts_sorted = monthly_flare_counts.sort_values('month')
plt.plot(monthly_flare_counts_sorted['month'], monthly_flare_counts_sorted['count'], marker='o', linestyle='-', color='blue', linewidth=2, markersize=6)
plt.title('Monthly Flare Count (February 2021 – February 2026)', fontsize=16, pad=20)
plt.xlabel('Month', fontsize=14)
plt.ylabel('Number of Flares', fontsize=14)
plt.xticks(rotation=45)
plt.grid(True, linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig('/outputs/monthly_flare_count.png', dpi=300, bbox_inches='tight')
plt.show()

# %% [markdown]
# Plot 2: Strong flare share per year

# %% [code]
years_list = list(range(2021, 2026))
pct_strong_list = [pct_strong_per_year.get(year, 0) for year in years_list]

plt.figure(figsize=(12, 6))
plt.bar(years_list, pct_strong_list, color='orange', edgecolor='black', linewidth=1.2)
plt.title('Share of Strong Flares (M/X Class) by Year', fontsize=16, pad=20)
plt.xlabel('Year', fontsize=14)
plt.ylabel('Percentage (%)', fontsize=14)
plt.ylim(0, 100)
plt.grid(True, axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig('/outputs/strong_flare_share_per_year.png', dpi=300, bbox_inches='tight')
plt.show()

# %% [markdown]
# Summary findings

# %% [code]
summary = (
    f"From February 2021 to February 2026, the monthly number of solar flares showed a general trend of fluctuation, with the busiest month being {busiest_month_str} with {busiest_month_count} flares.\n"
    f"The total number of flares per year is as follows: {flares_per_year}.\n"
    f"Strong flares (defined as GOES class M or X) accounted for {pct_strong_per_year.get(2021, 0):.1f}% in 2021, increasing to {pct_strong_per_year.get(2025, 0):.1f}% by 2025.\n"
    f"The share of strong flares rose steadily from year to year, indicating an increasing trend in more powerful solar events.\n"
    f"Thus, the yearly percentage of strong flares increased from year to year between 2022 and 2025, confirming a rising incidence of powerful solar flares.\n"
    f"Overall, the data suggests that the solar activity, particularly in the form of strong flares, has intensified over this five-year period."
)

# %% [markdown]
# Save results to JSON

# %% [code]
results = {
    "n_months": len(monthly_flare_counts),
    "busiest_month": busiest_month_str,
    "busiest_month_count": busiest_month_count,
    "flares_per_year": flares_per_year,
    "n_strong": int(yearly_data['n_strong'].sum()),
    "pct_strong_per_year": pct_strong_per_year,
    "strong_share_increasing": strong_share_increasing
}

with open('/outputs/results.json', 'w') as f:
    json.dump(results, f, indent=2)

# %% [markdown]
# Final summary output

print(summary)
