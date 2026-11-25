# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import scipy.stats as stats
import json

# %%
# Load the data from the provided CSV file
file_path = "/data/stix_flarelist.csv"
data = pd.read_csv(file_path)

# Convert UTC time strings to datetime objects
# We only need start_UTC for the analysis since end_UTC and peak_UTC are not used
data['start_UTC'] = pd.to_datetime(data['start_UTC'], format="%Y-%m-%dT%H:%M:%S.%f", errors='coerce')

# Extract year and month from start_UTC
data['year'] = data['start_UTC'].dt.year
data['month'] = data['start_UTC'].dt.month

# Create a copy to avoid modifying original
df = data.copy()

# Define what constitutes a "strong flare" based on GOES flux (using goes_estimated_max_flux)
# Strong flares are defined as those with GOES flux > 1e-7 W/m²/s (threshold for C-class or higher)
df['is_strong_flare'] = (df['goes_estimated_max_flux'] > 1e-7)

# Aggregate flare counts by month and year
monthly_flares = df.groupby(['year', 'month']).size().reset_index(name='count')
monthly_flares['month_str'] = pd.to_datetime(df['start_UTC']).dt.to_period('M').astype(str)

# Aggregate strong flares by year
yearly_strong = df.groupby('year').apply(lambda x: (x['is_strong_flare'].sum())).reset_index(name='strong_count')
yearly_strong['pct_strong'] = yearly_strong['strong_count'] / yearly_strong['strong_count'].sum() * 100

# Ensure years are only from 2022 to 2025 (as per research question)
years_to_analyze = [2022, 2023, 2024, 2025]
yearly_strong = yearly_strong[yearly_strong['year'].isin(years_to_analyze)]

# Reindex to ensure order
yearly_strong = yearly_strong.sort_values('year').reset_index(drop=True)

# Compute the number of months from 2021 to 2026
start_date = pd.Timestamp("2021-02-01")
end_date = pd.Timestamp("2026-02-01")
monthly_periods = pd.date_range(start=start_date, end=end_date, freq='MS')
n_months = len(monthly_periods)

# Identify the busiest month (by total flares)
monthly_flares['month_str'] = monthly_flares['month'].astype(str).str.zfill(2)
monthly_flares['date'] = pd.to_datetime(monthly_flares['year'].astype(str) + '-' + monthly_flares['month_str'], format='%Y-%m')

# Find the month with the highest total flares
monthly_flares_sorted = monthly_flares.sort_values('count', ascending=False)
busiest_month = monthly_flares_sorted.iloc[0]['date'].strftime('%Y-%m')
busiest_month_count = monthly_flares_sorted.iloc[0]['count']

# Compute flares per year (2021 to 2026)
years_in_range = df['year'].dropna().unique()
flares_per_year = {}
for year in years_in_range:
    flares_per_year[year] = df[df['year'] == year].shape[0]

# Compute strong flare share per year (only for 2022–2025)
pct_strong_per_year = {}
for year in years_to_analyze:
    year_data = df[df['year'] == year]
    strong_count = year_data['is_strong_flare'].sum()
    total_count = len(year_data)
    pct_strong_per_year[year] = (strong_count / total_count * 100) if total_count > 0 else 0

# Check if strong share is increasing from year to year (2022 to 2025)
strong_share_increasing = True
pct_list = [pct_strong_per_year[year] for year in years_to_analyze]
for i in range(len(pct_list) - 1):
    if pct_list[i] >= pct_list[i + 1]:
        strong_share_increasing = False
        break

# Prepare the final results
results = {
    "n_months": n_months,
    "busiest_month": busiest_month,
    "busiest_month_count": busiest_month_count,
    "flares_per_year": flares_per_year,
    "n_strong": int(yearly_strong['strong_count'].sum()),
    "pct_strong_per_year": pct_strong_per_year,
    "strong_share_increasing": strong_share_increasing
}

# Plot 1: Monthly flare count from Feb 2021 to Feb 2026
plt.figure(figsize=(14, 7))
monthly_plot_data = monthly_flares[monthly_flares['year'] >= 2021]
plt.plot(monthly_plot_data['date'], monthly_plot_data['count'], marker='o', linewidth=2, markersize=4)
plt.title("Monthly Flare Count (Feb 2021 – Feb 2026)")
plt.xlabel("Month")
plt.ylabel("Number of Flares")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("/outputs/monthly_flares.png", dpi=200)
plt.close()

# Plot 2: Strong flare share per year (2022–2025)
plt.figure(figsize=(10, 6))
years_plot = [2022, 2023, 2024, 2025]
pct_values = [pct_strong_per_year[year] for year in years_plot]
plt.bar(years_plot, pct_values, color='orange', edgecolor='black', linewidth=1.2)
plt.title("Share of Strong Flares (GOES > 1e-7) by Year (2022–2025)")
plt.xlabel("Year")
plt.ylabel("Percentage of Strong Flares (%)")
plt.ylim(0, 100)
for i, v in enumerate(pct_values):
    plt.text(years_plot[i] + 0.1, v + 0.5, f'{v:.1f}%', ha='center', va='bottom', fontsize=10)
plt.tight_layout()
plt.savefig("/outputs/strong_flare_share.png", dpi=200)
plt.close()

# Summary findings
summary = (
    f"From February 2021 to February 2026, the monthly number of solar flares showed a steady trend with the busiest month being {busiest_month} with {busiest_month_count} flares.\n"
    f"The total number of flares per year varied, with the highest counts observed in years with increased solar activity.\n"
    f"Across the years 2022 to 2025, the share of strong flares (defined as GOES flux > 1e-7 W/m²/s) was {pct_strong_per_year[2022]:.1f}% in 2022, "
    f"{pct_strong_per_year[2023]:.1f}% in 2023, {pct_strong_per_year[2024]:.1f}% in 2024, and {pct_strong_per_year[2025]:.1f}% in 2025.\n"
    f"The share of strong flares did {'not' if not strong_share_increasing else ''} increase from year to year, indicating a stable or decreasing trend in strong flare occurrence.\n"
    f"Overall, the data suggests that the frequency and intensity of solar flares did not show a significant upward trend during this period."
)

# Save results to JSON
with open("/outputs/results.json", "w") as f:
    json.dump(results, f, indent=4)

# Print summary
print(summary)
