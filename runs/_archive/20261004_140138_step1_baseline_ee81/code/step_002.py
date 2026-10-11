import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

os.makedirs('/outputs', exist_ok=True)

df = pd.read_csv('/data/stix_flarelist.csv')
df['date'] = pd.to_datetime(df['date'])

start_date = '2021-02-01'
end_date = '2026-02-01'
df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]

df['month'] = df['date'].dt.strftime('%Y-%m')
monthly_counts = df.groupby('month').size()

plt.figure()
plt.plot(monthly_counts.index, monthly_counts.values)
plt.title('Monthly Flare Counts (Feb 2021 - Feb 2026)')
plt.xlabel('Month')
plt.ylabel('Number of Flares')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('/outputs/monthly_flare_counts.png')
plt.close()

strong_flares = df[df['class'].isin(['M', 'X'])]
df['year'] = df['date'].dt.year
yearly_counts = df.groupby('year').size()
strong_yearly_counts = strong_flares.groupby('year').size()
pct_strong_per_year = (strong_yearly_counts / yearly_counts) * 100

plt.figure()
plt.bar(yearly_counts.index, pct_strong_per_year)
plt.title('Percentage of Strong Flares (M/X) per Year (2021-2026)')
plt.xlabel('Year')
plt.ylabel('Percentage of Strong Flares')
plt.ylim(0, 100)
plt.tight_layout()
plt.savefig('/outputs/strong_flare_percentage.png')
plt.close()

busiest_month = monthly_counts.idxmax()
busiest_month_count = monthly_counts.max()

flares_per_year = yearly_counts.to_dict()
n_strong = strong_yearly_counts.sum()
pct_strong_per_year_dict = pct_strong_per_year.to_dict()

years = sorted(yearly_counts.index)
pct_strong_list = [pct_strong_per_year_dict[y] for y in years]
is_increasing = all(pct_strong_list[i] < pct_strong_list[i+1] for i in range(len(pct_strong_list)-1))

print(f"Exploratory Data Analysis Report:")
print(f"Total flares in period: {len(df)}")
print(f"Busiest month: {busiest_month} with {busiest_month_count} flares")
print(f"Flares per year: {flares_per_year}")
print(f"Total strong flares (M/X): {n_strong}")
print(f"Percentage of strong flares per year: {pct_strong_per_year_dict}")
print(f"Strong share increasing over years: {is_increasing}")

n_months = len(monthly_counts)
results_json = (
    f"RESULTS_JSON: {{\"n_months\": {n_months}, "
    f"\"busiest_month\": \"{busiest_month}\", "
    f"\"busiest_month_count\": {busiest_month_count}, "
    f"\"flares_per_year\": {flares_per_year}, "
    f"\"n_strong\": {n_strong}, "
    f"\"pct_strong_per_year\": {pct_strong_per_year_dict}, "
    f"\"strong_share_increasing\": {is_increasing}}}"
)

print(results_json)
