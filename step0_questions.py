"""
Research questions helpful for measuring quality of product

The solar heartbeat. How did the Sun's flare activity change between February 2021 and
February 2026? Concretely: how did the number of flares per month evolve, and did strong flares
become a larger share of all flares throughout the time?

Precise definition:
How did the number of STIX flares per calendar month (by start_UTC) develop from Feb 2021 to Feb 2026,
 and did the share of strong flares (estimated GOES class M or X, goes_estimated_mean_class) increase from year to year?


Sub-answer	        Can be checked with	    True value (ground_truth.json)

Number of months	n_months	            61
Busiest month	    busiest_month	        2024-09 (1,724 flares)
Flares per year	    flares_per_year	        694 · 4,787 · 6,469 · 12,330 · 7,662 · 1,134
Total strong flares	n_strong_estimated_MX	1,637
% strong per year	pct_strong_per_year	    4.18 · 5.16 · 5.39 · 5.16 · 3.86 · (7.05, partial)

"""