import pandas as pd

df = pd.read_csv('/data/stix_flarelist.csv')
print(df.shape)
print(df.columns.tolist())
