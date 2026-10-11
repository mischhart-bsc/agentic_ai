import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

os.makedirs('/outputs', exist_ok=True)

df = pd.read_csv('/data/stix_flarelist.csv')
df['date'] = pd.to_datetime(df['date'])
start_date = pd.Timestamp('2021-02-01')
end_date = pd.Timestamp('2026-02-01')
df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]

df['month'] = df['date'].dt.to_period('M')
monthly_counts = df.groupby('month').size().reset_index(name='count')

df['is_strong'] = df['class'].isin(['M', 'X'])

yearly_counts = df.groupby(df['date'].dt.year).agg(
    total_flares=('date', 'count'),
    strong_flares=('is_strong', 'sum')
).reset_index()
yearly_counts['pct_strong'] = (yearly_counts['strong_flares'] / yearly_counts['total_flares']) * 100

plt.figure()
plt.plot(monthly_counts['month'], monthly_counts['count'])
plt.title('Monthly Flare Counts (Feb 2021 - Feb 2026)')
plt.xlabel('Month')
plt.ylabel('Number of Flares')
plt.savefig('/outputs/monthly_flare_counts.png')

plt.figure()
plt.plot(yearly_counts['date'], yearly_counts['pct_strong'])
plt.title('Yearly Share of Strong Flares (M/X) from 2021-2026')
plt.xlabel('Year')
plt.ylabel('Percentage of Strong Flares')
plt.savefig('/outputs/yearly_strong_flare_percentage.png')

n_months = len(monthly_counts)
busiest_month = monthly_counts.loc[monthly_counts['count'].idxmax(), 'month']
busiest_month_count = monthly_counts.loc[monthly_counts['count'].idxmax(), 'count']

flares_per_year = {}
for year in range(2021, 2027):
    year_data = df[df['date'].dt.year == year]
    flares_per_year[year] = len(year_data)

n_strong = df['is_strong'].sum()

pct_strong_per_year = {}
for year in range(2021, 2027):
    year_data = df[df['date'].dt.year == year]
    if len(year_data) > 0:
        pct = (year_data['is_strong'].sum() / len(year_data)) * 100
        pct_strong_per_year[year] = round(pct, 2)

strong_share_increasing = False
if len(yearly_counts) > 1:
    for i in range(1, len(yearly_counts)):
        if yearly_counts['pct_strong'].iloc[i] > yearly_counts['pct_strong'].iloc[i-1]:
            strong_share_increasing = True
            break

print("Exploratory Data Analysis Report:")
print(f"Total months analyzed: {n_months}")
print(f"Busiest month: {busiest_month} with {busiest_month_count} flares")
print(f"Flare counts per year: {flares_per_year}")
print(f"Total strong flares (M/X): {n_strong}")
print(f"Percentage of strong flares per year: {pct_strong_per_year}")
print(f"Strong flare share increasing: {strong_share_increasing}")

results_json = {
    "n_months": n_months,
    "busiest_month": str(busiest_month),
    "busiest_month_count": busiest_month_count,
    "flares_per_year": flares_per_year,
    "n_strong": n_strong,
    "pct_strong_per_year": pct_strong_per_year,
    "strong_share_increasing": strong_share_increasing
}

print(f"RESULTS_JSON: {results_json}")
