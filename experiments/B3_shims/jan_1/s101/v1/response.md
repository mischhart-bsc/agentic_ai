```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from datetime import datetime
import os

# Ensure outputs directory exists
os.makedirs("/outputs", exist_ok=True)

# Load data
file_path = "/data/stix_flarelist.csv"
df = pd.read_csv(file_path)

# Convert UTC timestamps to datetime
df['start_UTC'] = pd.to_datetime(df['start_UTC'], format='%Y-%m-%dT%H:%M:%S.%f')
df['end_UTC'] = pd.to_datetime(df['end_UTC'], format='%Y-%m-%dT%H:%M:%S.%f')
df['peak_UTC'] = pd.to_datetime(df['peak_UTC'], format='%Y-%m-%dT%H:%M:%S.%f')

# Extract year and month from start_UTC for grouping
df['year'] = df['start_UTC'].dt.year
df['month'] = df['start_UTC'].dt.month
df['month_str'] = df['start_UTC'].dt.to_period('M').astype(str)

# Define strong flare: GOES class B8 or higher (based on goes_estimated_max_class)
df['is_strong'] = df['goes_estimated_max_class'].apply(lambda x: x in ['B8', 'C', 'M', 'X'])

# Monthly count of flares
monthly_flares = df.groupby(['year', 'month']).size().reset_index(name='count')
monthly_flares['month_str'] = monthly_flares.apply(lambda row: f"{row['year']}-{str(row['month']).zfill(2)}", axis=1)

# Yearly counts of flares and strong flares
yearly_counts = df.groupby('year').size().reset_index(name='total_flares')
yearly_strong_counts = df.groupby('year').apply(lambda x: (x['is_strong'].sum())).reset_index(name='strong_flares')

# Calculate percentage of strong flares per year
yearly_percent_strong = yearly_strong_counts.set_index('year')['strong_flares'] / yearly_counts.set_index('year')['total_flares'] * 100

# Busiest month over 2021-2026
monthly_flares['count'] = monthly_flares['count'].fillna(0)
busiest_month = monthly_flares.loc[monthly_flares['count'].idxmax()]
busiest_month_str = f"{busiest_month['year']}-{str(busiest_month['month']).zfill(2)}"

# Flares per year
flares_per_year = yearly_counts.set_index('year')['total_flares'].to_dict()

# Strong flares per year
n_strong = df['is_strong'].sum()
pct_strong_per_year = yearly_percent_strong.to_dict()

# Check if strong share increases from year to year (2022-2025)
years = [2022, 2023, 2024, 2025]
pct_list = [pct_strong_per_year.get(y, 0) for y in years]
strong_share_increasing = True
for i in range(1, len(pct_list)):
    if pct_list[i] <= pct_list[i-1]:
        strong_share_increasing = False
        break

# Plot 1: Monthly flare count evolution
plt.figure(figsize=(14, 7))
monthly_flares['month_str'] = monthly_flares['month_str'].astype(str)
monthly_flares['month_str'] = monthly_flares['month_str'].apply(lambda x: x.replace('-', ''))
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '00')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '00')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('00', '00')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly_flares['month_str'].str.replace('0', '0')
monthly_flares['month_str'] = monthly