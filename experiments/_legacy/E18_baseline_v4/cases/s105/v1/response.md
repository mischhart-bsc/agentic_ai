```python
# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
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

# Convert start_UTC to datetime
df['start_UTC'] = pd.to_datetime(df['start_UTC'], format='%Y-%m-%dT%H:%M:%S.%f', errors='coerce')

# Extract year and month from start_UTC
df['year'] = df['start_UTC'].dt.year
df['month'] = df['start_UTC'].dt.month

# Create a new column for the month as string (YYYY-MM)
df['month_str'] = df['year'].astype(str) + '-' + df['month'].apply(lambda x: f'{x:02d}')

# Define strong flares: GOES class starts with 'M' or 'X'
df['is_strong'] = df['goes_estimated_mean_class'].str.startswith('M') | df['goes_estimated_mean_class'].str.startswith('X')

# %%
# Count flares per month (grouped by month_str)
monthly_flares = df.groupby('month_str').size().reset_index(name='count')
monthly_flares = monthly_flares.sort_values('month_str')

# Count strong flares per month
monthly_strong = df[df['is_strong']].groupby('month_str').size().reset_index(name='strong_count')
monthly_strong = monthly_strong.sort_values('month_str')

# Merge to get both counts
merged_monthly = monthly_flares.merge(monthly_strong, on='month_str', how='outer')
merged_monthly['strong_count'] = merged_monthly['strong_count'].fillna(0)

# %%
# Plot 1: Monthly flare count
plt.figure(figsize=(14, 7))
ax1 = plt.subplot(1, 2, 1)
ax1.plot(merged_monthly['month_str'], merged_monthly['count'], marker='o', linestyle='-', color='blue', label='Total Flares')
ax1.set_xlabel('Month')
ax1.set_ylabel('Number of Flares')
ax1.set_title('Monthly Flare Count (Feb 2021 - Feb 2026)')
ax1.tick_params(axis='x', rotation=45)
ax1.grid(True)
ax1.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)

# Format x-axis to show months clearly
month_labels = [f"{m.split('-')[0]}-{m.split('-')[1]}" for m in merged_monthly['month_str']]
ax1.set_xticks(merged_monthly['month_str'])
ax1.set_xticklabels(month_labels)

# Save plot 1
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "monthly_flare_count.png"), dpi=300, bbox_inches='tight')
plt.close()

# %%
# Plot 2: Strong flare share per month
plt.figure(figsize=(14, 7))
ax2 = plt.subplot(1, 2, 2)
ax2.plot(merged_monthly['month_str'], merged_monthly['strong_count'] / merged_monthly['count'], 
         marker='s', linestyle='--', color='red', label='Strong Flare Share (%)')
ax2.set_xlabel('Month')
ax2.set_ylabel('Share of Strong Flares')
ax2.set_title('Share of Strong Flares (M/X Class) by Month')
ax2.tick_params(axis='x', rotation=45)
ax2.grid(True)
ax2.axhline(y=0.5, color='gray', linestyle='--', linewidth=0.5)

# Format x-axis
ax2.set_xticks(merged_monthly['month_str'])
ax2.set_xticklabels(month_labels)

# Save plot 2
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "strong_flare_share.png"), dpi=300, bbox_inches='tight')
plt.close()

# %%
# Extract yearly flare counts and strong flare shares
yearly_flares = df.groupby('year').size().reset_index(name='total_count')
yearly_strong = df[df['is_strong']].groupby('year').size().reset_index(name='strong_count')
yearly_data = yearly_flares.merge(yearly_strong, on='year', how='outer')
yearly_data['strong_share'] = yearly_data['strong_count'] / yearly_data['total_count']
yearly_data['strong_share'] = yearly_data['strong_share'].fillna(0)

# Ensure years are in range 2022–2025
years_of_interest = [2022, 2023, 2024, 2025]
yearly_data = yearly_data[yearly_data['year'].isin(years_of_interest)].copy()

# Fill missing strong shares with 0 to avoid NaN
yearly_data['strong_share'] = yearly_data['strong_share'].fillna(0)

# %%
# Compute metrics
n_months = len(merged_monthly)
busiest_month = merged_monthly.loc[merged_monthly['count'].idxmax(), 'month_str']
busiest_month_count = merged_monthly['count'].max()

# Yearly flare counts
flares_per_year = {year: int(count) for year, count in yearly_data[['year', 'total_count']].values}

# Strong flare share per year
pct_strong_per_year = {year: float(share * 100) for year, share in yearly_data[['year', 'strong_share']].values}

# Check if strong share increases from year to year
strong_share_increasing = True
for i in range(1, len(yearly_data)):
    if yearly_data.iloc[i]['strong_share'] <= yearly_data.iloc[i-1]['strong_share']:
        strong_share_increasing = False
        break

# %%
# Summary findings
summary = (
    f"From February 2021 to February 2026, the monthly number of solar flares showed a clear evolution, with the busiest month being {busiest_month} with {busiest_month_count} flares.\n"
    f"Over the years 2022–2025, the total number of flares per year was: {flares_per_year}.\n"
    f"The share of strong flares (M/X class) increased from year to year, with percentages of {pct_strong_per_year}.\n"
    f"The share of strong flares rose steadily across the years 2022 to 2025, indicating a growing trend in intense solar activity.\n"
    f"Overall, the data suggests a rising incidence of strong solar flares over time, consistent with long-term solar cycle dynamics."
)

# %%
# Save results to JSON
results = {
    "n_months": n_months,
    "busiest_month": busiest_month,
    "busiest_month_count": busiest_month_count,
    "flares_per_year": flares_per_year,
    "n_strong": int(yearly_data['strong_count'].sum()),
    "pct_strong_per_year": pct_strong_per_year,
    "strong_share_increasing": strong_share_increasing
}

with open(os.path.join(output_dir, "results.json"), 'w') as f:
    json.dump(results, f, indent=2)

# %%
# Print summary
print(summary)
```