""" 
File for manual EDA, giving information about the data at hand
"""
import pandas as pd

df = pd.read_csv("data/stix_flarelist.csv", low_memory=False)

print(df.shape)
print(df.dtypes)
print(df.isna().sum())
"""
(33076, 40)
start_UTC                        str
end_UTC                          str
peak_UTC                         str
4-10 keV                       int64
10-15 keV                      int64
15-25 keV                      int64
25-50 keV                      int64
50-84 keV                      int64
bkg 4-10 keV                 float64
bkg 10-15 keV                float64
bkg 15-25 keV                float64
bkg 25-50 keV                float64
bkg 50-84 keV                float64
bkg_baseline_4-10 keV        float64
hpc_x_solo                   float64
hpc_y_solo                   float64
hpc_x_earth                  float64
hpc_y_earth                  float64
visible_from_earth            object
hgs_lon                      float64
hgs_lat                      float64
hgc_lon                      float64
hgc_lat                      float64
solo_position_lat            float64
solo_position_lon            float64
solo_position_AU_distance    float64
EAR_TDEL                     float64
GOES_class_time_of_flare         str
GOES_flux_time_of_flare      float64
att_in                          bool
flare_id                       int64
sidelobes_ratio              float64
goes_estimated_min_class         str
goes_estimated_max_class         str
goes_estimated_mean_class        str
goes_estimated_min_flux      float64
goes_estimated_max_flux      float64
goes_estimated_mean_flux     float64
error_with_imaging              bool
cpd_filename                     str
dtype: object
start_UTC                        0
end_UTC                          0
peak_UTC                         0
4-10 keV                         0
10-15 keV                        0
15-25 keV                        0
25-50 keV                        0
50-84 keV                        0
bkg 4-10 keV                     0
bkg 10-15 keV                    0
bkg 15-25 keV                    0
bkg 25-50 keV                    0
bkg 50-84 keV                    0
bkg_baseline_4-10 keV            0
hpc_x_solo                    2476
hpc_y_solo                    2476
hpc_x_earth                  17491
hpc_y_earth                  17491
visible_from_earth            2476
hgs_lon                       2476
hgs_lat                       2476
hgc_lon                       2476
hgc_lat                       2476
solo_position_lat                0
solo_position_lon                0
solo_position_AU_distance        0
EAR_TDEL                         0
GOES_class_time_of_flare       620
GOES_flux_time_of_flare          0
att_in                           0
flare_id                         0
sidelobes_ratio               2477
goes_estimated_min_class         0
goes_estimated_max_class         0
goes_estimated_mean_class        0
goes_estimated_min_flux          0
goes_estimated_max_flux          0
goes_estimated_mean_flux         0
error_with_imaging               0
cpd_filename                  1345
dtype: int64

"""

