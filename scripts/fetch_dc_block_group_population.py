#!/usr/bin/env python3
"""Fetch DC block group population from the Census ACS API.

Block groups are the finest Census geography with ACS data. No spatial
interpolation needed — block groups are native ACS units.

Outputs:
  bikeshare/seeds/dc_block_group_population.csv

Data source: ACS 5-year estimates, 2023 (covering 2019–2023).

Note: block group queries require county + tract as parent geographies.
DC has one county (FIPS 001), so the query is straightforward.

Usage:
    .venv/bin/python scripts/fetch_dc_block_group_population.py
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_block_group_population.csv"

_STATE_FIPS  = "11"
_COUNTY_FIPS = "001"
_ACS_YEAR    = "2023"

_VARS = {
    "B01003_001E": "population",
    "B11001_001E": "households",
    "B19013_001E": "median_household_income",
}


def main() -> None:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        print(
            "\nERROR: Census API key required.\n"
            "  1. Get a free key at: https://api.census.gov/data/key_signup.html\n"
            "  2. Add to .env in the repo root:\n"
            "       CENSUS_API_KEY=your_key_here\n"
            "  3. Re-run this script.\n"
        )
        sys.exit(1)

    var_list = ",".join(_VARS.keys())
    # Block groups require county + tract as parent geographies.
    url = (
        f"https://api.census.gov/data/{_ACS_YEAR}/acs/acs5"
        f"?get=NAME,{var_list}"
        f"&for=block%20group:*"
        f"&in=state:{_STATE_FIPS}%20county:{_COUNTY_FIPS}%20tract:*"
        f"&key={key}"
    )
    print(f"Fetching ACS {_ACS_YEAR} 5-year data for DC block groups...")
    req = urllib.request.Request(url, headers={"User-Agent": "bikeshare-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        rows = json.load(resp)

    header, *data = rows
    df = pd.DataFrame(data, columns=header)
    print(f"  {len(df)} block groups returned")

    # Reconstruct 12-digit GEOID: state(2) + county(3) + tract(6) + block_group(1).
    df["bg_geoid"] = df["state"] + df["county"] + df["tract"] + df["block group"]

    for code, name in _VARS.items():
        df[name] = pd.to_numeric(df[code], errors="coerce")

    df["median_household_income"] = df["median_household_income"].where(
        df["median_household_income"] > 0
    )

    df["population"] = df["population"].round(0).astype("Int64")
    df["households"] = df["households"].round(0).astype("Int64")

    result = df[["bg_geoid", "population", "households", "median_household_income"]] \
        .sort_values("bg_geoid") \
        .reset_index(drop=True)

    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(result)} rows)")
    print()
    print("Sample (top 5 by population):")
    print(result.sort_values("population", ascending=False).head(5).to_string(index=False))


if __name__ == "__main__":
    main()
