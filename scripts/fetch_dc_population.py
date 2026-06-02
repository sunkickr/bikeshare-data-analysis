#!/usr/bin/env python3
"""Fetch DC census-tract population from the Census ACS API and spatially
join it to the frozen OSM neighbourhood polygons.

Outputs:
  bikeshare/seeds/dc_neighborhood_population.csv

Methodology: area-weighted interpolation. Each census tract's population is
split across whichever neighbourhoods it overlaps, proportional to the share
of the tract's area that falls inside each neighbourhood. Median household
income is population-weighted across the tracts that contribute to each
neighbourhood.

Data source: ACS 5-year estimates, 2023 (covering 2019–2023).
Census TIGER tract boundaries: 2023 vintage.

Usage:
    .venv/bin/python scripts/fetch_dc_population.py
"""
import json
import os
import sys
import urllib.request
import warnings
from pathlib import Path

# Load .env from repo root if present (key never committed — .env is gitignored).
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

import geopandas as gpd
import pandas as pd

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).parent.parent
GEO_IN    = REPO_ROOT / "data" / "geo" / "dc_neighborhoods_osm.geojson"
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_neighborhood_population.csv"

# DC FIPS code; ACS 5-year 2023.
_STATE_FIPS  = "11"
_ACS_YEAR    = "2023"
_METRIC_CRS  = 32618

# ACS variable codes.
_VARS = {
    "B01003_001E": "population",
    "B11001_001E": "households",
    "B19013_001E": "median_household_income",
}


def _fetch_acs() -> pd.DataFrame:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        print(
            "\nERROR: Census API key required.\n"
            "  1. Get a free key at: https://api.census.gov/data/key_signup.html\n"
            "     (fill in name + email — key arrives in minutes)\n"
            "  2. Add to .env in the repo root:\n"
            "       CENSUS_API_KEY=your_key_here\n"
            "  3. Re-run:  CENSUS_API_KEY=your_key .venv/bin/python scripts/fetch_dc_population.py\n"
        )
        sys.exit(1)

    var_list = ",".join(_VARS.keys())
    url = (
        f"https://api.census.gov/data/{_ACS_YEAR}/acs/acs5"
        f"?get=NAME,{var_list}&for=tract:*&in=state:{_STATE_FIPS}&key={key}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "bikeshare-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        rows = json.load(resp)

    header, *data = rows
    df = pd.DataFrame(data, columns=header)

    # Build GEOID to join against TIGER boundaries.
    df["GEOID"] = df["state"] + df["county"] + df["tract"]

    for code, name in _VARS.items():
        df[name] = pd.to_numeric(df[code], errors="coerce")

    # Negative values (-666666666) indicate suppressed/missing data.
    df["median_household_income"] = df["median_household_income"].where(
        df["median_household_income"] > 0
    )
    return df[["GEOID", "population", "households", "median_household_income"]]


def _fetch_tiger_tracts() -> gpd.GeoDataFrame:
    tiger_url = (
        "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/"
        f"tl_2023_{_STATE_FIPS}_tract.zip"
    )
    print(f"  Downloading TIGER tract boundaries for DC...")
    tracts = gpd.read_file(tiger_url)
    return tracts[["GEOID", "geometry"]]


def _area_weighted_join(
    nbhds: gpd.GeoDataFrame,
    tracts: gpd.GeoDataFrame,
    pop_df: pd.DataFrame,
) -> pd.DataFrame:
    """Area-weighted interpolation of tract population onto neighbourhood polygons."""
    tracts_m = tracts.to_crs(_METRIC_CRS)
    nbhds_m  = nbhds.to_crs(_METRIC_CRS)

    tracts_m["tract_area"] = tracts_m.geometry.area

    # Merge population data onto tract geometries.
    tracts_m = tracts_m.merge(pop_df, on="GEOID", how="left")

    # Compute pairwise intersections.
    intersection = gpd.overlay(nbhds_m, tracts_m, how="intersection")
    intersection["intersect_area"] = intersection.geometry.area
    intersection["weight"] = (
        intersection["intersect_area"] / intersection["tract_area"]
    )

    # Weighted sums for additive fields.
    for col in ("population", "households"):
        intersection[f"w_{col}"] = intersection[col] * intersection["weight"]

    # Population-weighted income (income is a median — weighted avg is an approximation).
    intersection["w_income_num"] = (
        intersection["median_household_income"] * intersection["w_population"]
    )

    agg = intersection.groupby("neighborhood_name").agg(
        population      = ("w_population",  "sum"),
        households      = ("w_households",  "sum"),
        income_num      = ("w_income_num",  "sum"),
        income_pop      = ("w_population",  "sum"),
    )
    agg["median_household_income"] = (agg["income_num"] / agg["income_pop"]).round(0)
    agg["population"]  = agg["population"].round(0).astype(int)
    agg["households"]  = agg["households"].round(0).astype(int)

    return agg[["population", "households", "median_household_income"]].reset_index()


def main() -> None:
    print("Fetching ACS population data for DC census tracts...")
    pop_df = _fetch_acs()
    print(f"  {len(pop_df)} tracts fetched")

    tracts = _fetch_tiger_tracts()
    print(f"  {len(tracts)} tract boundaries loaded")

    print("Loading frozen neighbourhood polygons...")
    nbhds = gpd.read_file(GEO_IN)[["neighborhood_name", "geometry"]]

    print("Running area-weighted spatial join...")
    result = _area_weighted_join(nbhds, tracts, pop_df)

    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    result.sort_values("neighborhood_name").to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(result)} rows)")
    print()
    print("Sample:")
    print(result.sort_values("population", ascending=False).head(10).to_string(index=False))


if __name__ == "__main__":
    main()
