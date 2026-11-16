import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import os
from datetime import datetime

# Set output directory
os.makedirs('/outputs', exist_ok=True)

# Load data
file_path = '/data/stix_flarelist.csv'
df = pd.read_csv(file_path)

# Convert date column to datetime (assuming 'date' column exists)
# If not, assume the first column is date
date_col = 'date'
if date_col not in df.columns:
    # Try to detect date column by parsing first column
    date_col = df.columns[0]
    # If still not found, raise error
    if not isinstance(date_col, str):
        raise ValueError("No valid date column found in the dataset.")

df[date_col] = pd.to_datetime(df[date_col], errors='coerce')

# Filter data from February 2021 to February 2026
df_filtered = df[(df[date_col] >= '2021-02-01') & (df[date_col] <= '2026-02-29')]

# Ensure 'strength' column exists and is numeric
if 'strength' not in df_filtered.columns:
    raise ValueError("Missing 'strength' column in data; expected for strong flares.")

# Convert strength to numeric
df_filtered['strength'] = pd.to_numeric(df_filtered['strength'], errors='coerce')

# Remove rows with invalid strength
df_filtered = df_filtered.dropna(subset=['strength'])

# Create monthly bins
df_filtered['year_month'] = df_filtered[date_col].dt.to_period('M')

# Group by year-month and count flares
monthly_summary = df_filtered.groupby('year_month').size().reset_index(name='flare_count')

# Calculate strong flares (say strength > 1000)
df_filtered['is_strong'] = (df_filtered['strength'] > 1000)
strong_flares = df_filtered['is_strong'].sum()

# Yearly breakdown
yearly_summary = df_filtered.groupby(df_filtered[date_col].dt.year).size().reset_index(name='total_flares')
yearly_summary['pct_strong'] = (df_filtered.groupby(df_filtered[date_col].dt.year).apply(lambda x: (x['is_strong'].sum() / x.shape[0]) * 100)).reset_index(name='pct_strong')
yearly_summary = yearly_summary.merge(yearly_summary[['year', 'pct_strong']], left_on='year', right_on='year', suffixes=('', '_right'))

# Clean percentage data
yearly_summary['pct_strong'] = yearly_summary['pct_strong'].fillna(0)

# Create yearly strong flare percentage
pct_strong_per_year = yearly_summary.set_index('year')['pct_str
