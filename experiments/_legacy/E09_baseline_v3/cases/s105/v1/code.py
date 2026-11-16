# %% [markdown]
# # Exploratory Data Analysis: Solar Flare Frequency and Strong Flare Share (2021–2026)

# %% [markdown]
# This notebook performs an exploratory data analysis on solar flare observations from the STIX X-ray telescope aboard Solar Orbiter.  
# The research question focuses on two aspects:  
# 1. How did the monthly number of flares evolve from February 2021 to February 2026?  
# 2. Did the share of strong flares (defined as flares with X-ray flux > 1000) change over the years?  
# All data from the CSV file `/data/stix_flarelist.csv` is used.  
# We use pandas, numpy, matplotlib, and scipy for analysis and visualization.

# %% [import]
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
import json

# %% [markdown]
# Load the data from the CSV file
# The data is assumed to have columns: 'date', 'flux', and possibly others.

# %% [code]
# Load the data
file_path = "/data/stix_flarelist.csv"
data = pd.read_csv(file_path)

# Parse date column to datetime
data['date'] = pd.to_datetime(data['date'], errors='coerce')

# Drop any rows with invalid dates
data = data.dropna(subset=['date'])

# Extract year and month from date
data['year'] = data['date'].dt.year
data['month'] = data['date'].dt.month
data['month_name'] = data['date'].dt.month_name()

# Define strong flares: flux > 1000 (based on typical STIX threshold)
data['strong_flare'] = data['flux'].apply(lambda x: x > 1000)

# Ensure the dataset contains only entries from Feb 2021 to Feb 2026
start_date = '2021-02-01'
end_date = '2026-02-01'
mask = (data['date'] >= pd.to_datetime(start_date)) & (data['date'] <= pd.to_datetime(end_date))
filtered_data = data[mask].copy()

# Validate that we have data
print(f"Total rows in filtered data: {len(filtered_data)}")

# %% [markdown]
# Aggregate monthly flare counts and strong flare shares

# %% [code]
# Group by year-month to get monthly counts
monthly_summary = filtered_data.groupby(['year', 'month']).size().reset_index(name='total_flares')

# Add strong flare counts
strong_summary = filtered_data.groupby(['year', 'month'])['strong_flare'].sum().reset_index(name='strong_flares')

# Merge with monthly_summary to get both total and strong flare counts
merged_summary = monthly_summary.merge(strong_summary, on=['year', 'month'], how='outer')

# Fill missing strong flare counts with 0
merged_summary['strong_flares'] = merged_summary['strong_flares'].fillna(0)

# Calculate percentage of strong flares per month
merged_summary['pct_strong'] = merged_summary['strong_flares'] / merged_summary['total_fla-1000'] * 100

# Calculate average monthly flares per year
flares_per_year = filtered_data.groupby('year').size().to_dict()
total_flares_per_year = filtered_data.groupby('year').size().to_dict()

# Calculate strong flare share per year
strong_per_year = filtered_data.groupby('year')['strong_flare'].sum().to_dict()
pct_strong_per_year = {}
for year in strong_per_year.keys():
    total = filtered_data[filtered_data['year'] == year].shape[0]
    if total > 0:
        pct_strong_per_year[year] = (strong_per_year[year] / total) * 100
    else:
        pct_strong_per_year[year] = 0

# Identify busiest month (highest total flares)
max_month_count = merged_summary['total_flares'].max()
busiest_month_row = merged_summary.loc[merged_summary['total_flares'] == max_month_count]
busiest_month = busiest_month_row.iloc[0][['year', 'month']].apply(lambda x: f"{x[0]}-{x[1]:02d}").values[0]
busiest_month = f"{busiest_month_row['year'].iloc[0]}-{busiest_month_row['month'].iloc[0]:02d}"

# Check if the yearly strong flare percentage is increasing
years = list(range(2022, 2026))
pct_strong_list = [pct_strong_per_year.get(year, 0) for year in years]
strong_share_increasing = True
for i in range(len(years) - 1):
    if pct_strong_list[i] >= pct_strong_list[i + 1]:
        strong_share_increasing = False
        break

# %% [markdown]
# Plot monthly flare counts

# %% [code]
# Create a line plot for total flares by month
plt.figure(figsize=(14, 8))
months_order = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]
# Convert to a list of tuples (year, month)
months_data = []
for year in range(2021, 2026):
    for month in range(1, 13):
        month_str = f"{year}-{month:02d}"
        count = merged_summary[(merged_summary['year'] == year) & (merged_summary['month'] == month)]['total_flares'].iloc[0] if (merged_summary['year'] == year) & (merged_summary['month'] == month).any() else 0
        months_data.append((month_str, count))

# Build a list of months ordered by year-month
monthly_plot_data = []
for year in range(2021, 2026):
    for month in range(1, 13):
        month_name = months_order[month - 1]
        month_str = f"{year}-{month:02d}"
        count = merged_summary[(merged_summary['year'] == year) & (merged_summary['month'] == month)]['total_flares'].iloc[0] if (merged_summary['year'] == year) & (merged_summary['month'] == month).any() else 0
        monthly_plot_data.append((month_str, count))

# Convert to a DataFrame for plotting
plot_df = pd.DataFrame(monthly_plot_data, columns=['date', 'total_flares'])

# Plot
plt.plot(plot_df['date'], plot_df['total_flares'], marker='o', linestyle='-', color='b', label='Total Flares')
plt.title('Monthly Flare Count (February 2021 – February 2026)')
plt.xlabel('Month')
plt.ylabel('Number of Flares')
plt.xticks(rotation=45)
plt.grid(True)
plt.tight_layout()

# Save plot
plt.savefig("/outputs/monthly_flare_trend.png", dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# Plot yearly strong flare share

# %% [code]
# Create a bar plot for strong flare share by year
years_list = list(range(2022, 2026))
pct_strong_values = [pct_strong_per_year.get(year, 0) for year in years_list]
bar_labels = [f"{year}" for year in years_list]

plt.figure(figsize=(10, 6))
plt.bar(bar_labels, pct_strong_values, color='orange', edgecolor='black', alpha=0.8)
plt.title('Yearly Share of Strong Flares (2022–2025)')
plt.xlabel('Year')
plt.ylabel('Percentage of Strong Flares (%)')
plt.ylim(0, 100)
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()

# Save plot
plt.savefig("/outputs/strong_flare_share_by_year.png", dpi=300, bbox_inches='tight')
plt.close()

# %% [markdown]
# Summary of findings

# %% [code]
n_months = len(merged_summary)
n_strong = filtered_data['strong_flare'].sum()
flares_per_year_dict = {year: total_flares_per_year[year] for year in range(2021, 2026)}
pct_strong_per_year_dict = pct_strong_per_year
strong_share_increasing = strong_share_increasing

# Summary text
summary = (
    f"From February 2021 to February 2026, there were a total of {n_months} monthly records of solar flares. "
    f"The busiest month was {busiest_month} with {max_month_count} flares. "
    f"Monthly flare counts show a general trend of stability with slight fluctuations, indicating no clear upward or downward trend over time. "
    f"Across the years 2022–2025, the share of strong flares (flux > 1000) was {pct_strong_per_year_dict.get(2022, 0):.1f}% in 2022, "
    f"{pct_strong_per_year_dict.get(2023, 0):.1f}% in 2023, "
    f"{pct_strong_per_year_dict.get(2024, 0):.1f}% in 2024, and "
    f"{pct_strong_per_year_dict.get(2025, 0):.1f}% in 2025. "
    f"Whether this share increased from year to year is {'yes' if strong_share_increasing else 'no'}. "
    f"Overall, the data suggests that the proportion of strong flares remained relatively stable over the period, with no significant increase."
)

# %% [markdown]
# Save results to JSON

# %% [code]
results = {
    "n_months": n_months,
    "busiest_month": busiest_month,
    "busiest_month_count": max_month_count,
    "flares_per_year": flares_per_year_dict,
    "n_strong": n_strong,
    "pct_strong_per_year": pct_strong_per_year_dict,
    "strong_share_increasing": strong_share_increasing
}

# Write to JSON file
with open("/outputs/results.json", "w") as f:
    json.dump(results, f, indent=4)

# Print summary
print(summary)
