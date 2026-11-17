# %% [markdown]
# # Exploratory Data Analysis: Solar Flare Trends (2021–2026)

# %% [markdown]
# This notebook performs an exploratory data analysis on solar flares observed by the STIX instrument on the Solar Orbiter, focusing on the evolution of monthly flare counts and the share of strong flares from February 2021 to February 2026.

# %% [markdown]
# ## Step 1: Load and Inspect Data

# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import scipy.stats as stats
import os

# Set output directory
output_dir = "/outputs/"
os.makedirs(output_dir, exist_ok=True)

# Load the data
file_path = "/data/stix_flarelist.csv"
df = pd.read_csv(file_path)

# Display first few rows to understand structure
print("First 5 rows of the dataset:")
print(df.head())

# %% [markdown]
# ## Step 2: Extract Date Information and Clean Time Columns

# %%
# Convert start_UTC to datetime
df['start_UTC'] = pd.to_datetime(df['start_UTC'], format='%Y-%m-%dT%H:%M:%S.%f', errors='coerce')

# Extract year and month from start_UTC
df['year'] = df['start_UTC'].dt.year
df['month'] = df['start_UTC'].dt.month

# Create a month-year column for grouping
df['month_year'] = df['year'].astype(str) + '-' + df['month'].astype(str).apply(lambda x: f'{x:02d}')

# Verify the data has valid timestamps
print(f"Total rows: {len(df)}")
print(f"Missing start_UTC: {df['start_UTC'].isna().sum()}")

# %% [markdown]
# ## Step 3: Count Flares by Month and Year

# %%
# Count total flares per month-year
monthly_counts = df.groupby(['month_year']).size().reset_index(name='count')
monthly_counts['month_year'] = monthly_counts['month_year'].str.replace('0', '00', regex=False)

# Convert to a pivot for visualization
monthly_counts_sorted = monthly_counts.sort_values('month_year')

# Calculate total flares per year
flares_per_year = df.groupby('year').size().to_dict()
flares_per_year = {year: count for year, count in flares_per_year.items()}

# %% [markdown]
# ## Step 4: Define "Strong Flare" Criteria

# %%
# Based on GOES flux, define strong flares
# GOES class B4 and above are considered strong (from B4 to X-class)
# GOES flux values: B4 = ~4e-7, B8 = ~8e-7, X-class > 8e-7
# We'll define strong flares as those with GOES estimated flux >= 4e-7 (B4)

# Ensure GOES flux is numeric and clean
df['goes_estimated_min_flux'] = pd.to_numeric(df['goes_estimated_min_flux'], errors='coerce')
df['goes_estimated_max_flux'] = pd.to_numeric(df['goes_estimated_max_flux'], errors='coerce')

# Define strong flare: min flux >= 4e-7 (B4 class)
df['is_strong'] = (df['goes_estimated_min_flux'] >= 4e-7)

# Count strong flares per year
strong_per_year = df[df['is_strong']].groupby('year').size().to_dict()
strong_per_year = {year: count for year, count in strong_per_year.items() if count > 0}

# If no strong flares exist for a year, default to 0
for year in range(2021, 2026):
    if year not in strong_per_year:
        strong_per_year[year] = 0

# Calculate percentage of strong flares per year
pct_strong_per_year = {}
for year in range(2021, 2026):
    total = df[df['year'] == year].shape[0]
    strong = strong_per_year.get(year, 0)
    if total > 0:
        pct_strong_per_year[year] = strong / total * 100
    else:
        pct_strong_per_year[year] = 0

# %% [markdown]
# ## Step 5: Identify Busiest Month

# %%
# Find the month with the highest number of flares
max_month_count = monthly_counts['count'].max()
busiest_month = monthly_counts[monthly_counts['count'] == max_month_count]['month_year'].iloc[0]

# %% [markdown]
# ## Step 6: Plot Monthly Flare Counts

# %%
# Plot monthly flare counts
plt.figure(figsize=(14, 7))
plt.plot(monthly_counts['month_year'], monthly_counts['count'], marker='o', linestyle='-', color='blue', linewidth=2, markersize=6)
plt.xticks(rotation=45)
plt.title('Monthly Solar Flare Count (Feb 2021 – Feb 2026)', fontsize=14, pad=20)
plt.xlabel('Month-Year', fontsize=12)
plt.ylabel('Number of Flares', fontsize=12)
plt.grid(True, linestyle='--', alpha=0.5)
plt.tight_layout()

# Save plot
plt.savefig(os.path.join(output_dir, "monthly_flare_counts.png"), dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# ## Step 7: Plot Share of Strong Flares by Year

# %%
# Create a line plot of strong flare share by year
years = list(range(2021, 2026))
pct_values = [pct_strong_per_year.get(year, 0) for year in years]

plt.figure(figsize=(12, 6))
plt.plot(years, pct_values, marker='s', linestyle='-', color='red', linewidth=2, markersize=6)
plt.title('Share of Strong Flares (GOES B4+) by Year', fontsize=14, pad=20)
plt.xlabel('Year', fontsize=12)
plt.ylabel('Percentage of Strong Flares (%)', fontsize=12)
plt.ylim(0, 100)
plt.grid(True, linestyle='--', alpha=0.5)
plt.xticks(years)
plt.tight_layout()

# Save plot
plt.savefig(os.path.join(output_dir, "strong_flare_share_by_year.png"), dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# ## Step 8: Check if Strong Flare Share is Increasing Across Years

# %%
# Check if the yearly percentage of strong flares rises from 2021 to 2025
strong_share_increasing = True
for i in range(2021, 2025):
    if pct_strong_per_year.get(i+1, 0) <= pct_strong_per_year.get(i, 0):
        strong_share_increasing = False
        break

# %% [markdown]
# ## Step 9: Summary of Findings

# %%
# Final summary
n_months = len(monthly_counts)
busiest_month = busiest_month
busiest_month_count = max_month_count
flares_per_year_dict = flares_per_year
n_strong = sum(strong_per_year.values())
pct_strong_per_year_dict = pct_strong_per_year
strong_share_increasing_bool = strong_share_increasing

# %% [markdown]
# ## Step 10: Save Results to JSON

# %%
import json

results = {
    "n_months": n_months,
    "busiest_month": busiest_month,
    "busiest_month_count": busiest_month_count,
    "flares_per_year": flares_per_year_dict,
    "n_strong": n_strong,
    "pct_strong_per_year": pct_strong_per_year_dict,
    "strong_share_increasing": strong_share_increasing_bool
}

with open(os.path.join(output_dir, "results.json"), 'w') as f:
    json.dump(results, f, indent=2)

# Print final summary
print(f"Number of months analyzed: {n_months}")
print(f"Busiest month: {busiest_month} with {busiest_month_count} flares")
print(f"Total flares per year: {flares_per_year_dict}")
print(f"Total strong flares (GOES B4+): {n_strong}")
print(f"Percentage of strong flares by year: {pct_strong_per_year_dict}")
print(f"Did the share of strong flares increase from year to year? {'Yes' if strong_share_increasing else 'No'}")
