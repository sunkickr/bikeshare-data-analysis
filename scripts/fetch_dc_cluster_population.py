#!/usr/bin/env python3
"""Fetch DC census-tract population and spatially join it to the frozen
Neighborhood Cluster polygons (area-weighted interpolation).

Outputs:
  bikeshare/seeds/dc_cluster_population.csv

Requires CENSUS_API_KEY in environment or .env file.
See scripts/fetch_dc_population.py for the same logic applied to OSM boundaries.

Usage:
    .venv/bin/python scripts/fetch_dc_cluster_population.py
"""
import json
import os
import sys
import urllib.request
import warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd

warnings.filterwarnings("ignore")

# Load .env from repo root if present.
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

REPO_ROOT = Path(__file__).parent.parent
GEO_IN    = REPO_ROOT / "data" / "geo" / "dc_clusters.geojson"
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_cluster_population.csv"

_STATE_FIPS = "11"
_ACS_YEAR   = "2023"
_METRIC_CRS = 32618

_VARS = {
    "B01003_001E": "population",
    "B11001_001E": "households",
    "B19013_001E": "median_household_income",
}


def _fetch_acs() -> pd.DataFrame:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        print("\nERROR: CENSUS_API_KEY not set. Add it to .env in the repo root.\n")
        sys.exit(1)

    var_list = ",".join(_VARS.keys())
    url = (
        f"https://api.census.gov/data/{_ACS_YEAR}/acs/acs5"
        f"?get=NAME,{var_list}&for=tract:*&in=state:{_STATE_FIPS}&key={key}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "bikeshare-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        header, *data = json.load(resp)

    df = pd.DataFrame(data, columns=header)
    df["GEOID"] = df["state"] + df["county"] + df["tract"]
    for code, name in _VARS.items():
        df[name] = pd.to_numeric(df[code], errors="coerce")
    df["median_household_income"] = df["median_household_income"].where(
        df["median_household_income"] > 0
    )
    return df[["GEOID", "population", "households", "median_household_income"]]


def _fetch_tiger() -> gpd.GeoDataFrame:
    url = (
        f"https://www2.census.gov/geo/tiger/TIGER2023/TRACT/"
        f"tl_2023_{_STATE_FIPS}_tract.zip"
    )
    print("  Downloading TIGER tract boundaries...")
    return gpd.read_file(url)[["GEOID", "geometry"]]


def _area_weighted_join(
    boundaries: gpd.GeoDataFrame,
    tracts: gpd.GeoDataFrame,
    pop_df: pd.DataFrame,
    id_col: str,
) -> pd.DataFrame:
    tracts_m = tracts.to_crs(_METRIC_CRS)
    bounds_m = boundaries.to_crs(_METRIC_CRS)
    tracts_m["tract_area"] = tracts_m.geometry.area
    tracts_m = tracts_m.merge(pop_df, on="GEOID", how="left")

    ix = gpd.overlay(bounds_m, tracts_m, how="intersection")
    ix["intersect_area"] = ix.geometry.area
    ix["weight"]         = ix["intersect_area"] / ix["tract_area"]

    for col in ("population", "households"):
        ix[f"w_{col}"] = ix[col] * ix["weight"]

    ix["w_income_num"] = ix["median_household_income"] * ix["w_population"]

    agg = ix.groupby(id_col).agg(
        population = ("w_population", "sum"),
        households = ("w_households", "sum"),
        income_num = ("w_income_num", "sum"),
        income_pop = ("w_population", "sum"),
    )
    agg["median_household_income"] = (agg["income_num"] / agg["income_pop"]).round(0)
    agg["population"]  = agg["population"].round(0).astype(int)
    agg["households"]  = agg["households"].round(0).astype(int)
    return agg[["population", "households", "median_household_income"]].reset_index()


def main() -> None:
    print("Fetching ACS population data...")
    pop_df = _fetch_acs()
    print(f"  {len(pop_df)} tracts")

    tracts = _fetch_tiger()
    print(f"  {len(tracts)} tract boundaries")

    print("Loading frozen cluster polygons...")
    clusters = gpd.read_file(GEO_IN)[["cluster_id", "geometry"]]

    print("Running area-weighted spatial join...")
    result = _area_weighted_join(clusters, tracts, pop_df, id_col="cluster_id")

    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    result.sort_values("cluster_id").to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(result)} rows)")
    print()
    print(result.sort_values("population", ascending=False).head(8).to_string(index=False))


if __name__ == "__main__":
    main()
