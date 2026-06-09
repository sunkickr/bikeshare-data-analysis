#!/usr/bin/env python3
"""Fetch DC census-tract population directly from the Census ACS API.

Unlike the neighbourhood and cluster population scripts, no spatial
interpolation is needed here — tracts are the native ACS unit, so the
figures are exact (subject only to ACS survey margin of error).

Outputs:
  bikeshare/seeds/dc_census_tract_population.csv

Data source: ACS 5-year estimates, 2023 (covering 2019–2023).
Variables: total population, households, median household income.

Usage:
    .venv/bin/python scripts/fetch_dc_census_tract_population.py
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

# Load .env from repo root if present (key never committed — .env is gitignored).
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_census_tract_population.csv"

_STATE_FIPS = "11"
_ACS_YEAR   = "2023"

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
    url = (
        f"https://api.census.gov/data/{_ACS_YEAR}/acs/acs5"
        f"?get=NAME,{var_list}&for=tract:*&in=state:{_STATE_FIPS}&key={key}"
    )
    print(f"Fetching ACS {_ACS_YEAR} 5-year data for DC census tracts...")
    req = urllib.request.Request(url, headers={"User-Agent": "bikeshare-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        rows = json.load(resp)

    header, *data = rows
    df = pd.DataFrame(data, columns=header)
    print(f"  {len(df)} tracts returned")

    # Reconstruct 11-digit GEOID: state(2) + county(3) + tract(6).
    df["tract_geoid"] = df["state"] + df["county"] + df["tract"]

    for code, name in _VARS.items():
        df[name] = pd.to_numeric(df[code], errors="coerce")

    # Census suppresses low-count cells with -666666666.
    df["median_household_income"] = df["median_household_income"].where(
        df["median_household_income"] > 0
    )

    df["population"] = df["population"].round(0).astype("Int64")
    df["households"] = df["households"].round(0).astype("Int64")

    result = df[["tract_geoid", "population", "households", "median_household_income"]] \
        .sort_values("tract_geoid") \
        .reset_index(drop=True)

    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(result)} rows)")
    print()
    print("Sample (top 5 by population):")
    print(result.sort_values("population", ascending=False).head(5).to_string(index=False))


if __name__ == "__main__":
    main()
