"""Loads the STIX-CSV once to data/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # project folder: config.py, src/
import urllib.request

import config  # noqa: E402
URL = ("https://raw.githubusercontent.com/hayesla/stix_flarelist_science/main/"
       "STIX_flarelist_w_locations_20210214_20260228_version1_python.csv")
config.DATA_DIR.mkdir(exist_ok=True)
urllib.request.urlretrieve(URL, config.DATA_DIR / config.DATA_FILE)
print("OK:", config.DATA_DIR / config.DATA_FILE)
