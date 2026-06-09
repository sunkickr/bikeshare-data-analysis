#!/usr/bin/env python3
"""Freeze DC Census tract polygons from TIGER 2023 into two outputs:

  data/geo/dc_census_tracts.geojson     — polygon file for the dashboard map
  bikeshare/seeds/dc_census_tracts.csv  — tabular metadata for dbt

Source: Census Bureau TIGER/Line 2023, DC (state FIPS 11).

Run this once to snapshot the boundaries. Re-run only when you want to
deliberately update to a newer TIGER vintage.

Usage:
    .venv/bin/python scripts/freeze_dc_census_tracts.py
"""
from pathlib import Path

import geopandas as gpd

REPO_ROOT = Path(__file__).parent.parent
GEO_OUT   = REPO_ROOT / "data" / "geo" / "dc_census_tracts.geojson"
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_census_tracts.csv"

_TIGER_URL  = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_11_tract.zip"
_METRIC_CRS = 32618


def main() -> None:
    print("Downloading TIGER 2023 tract boundaries for DC...")
    gdf = gpd.read_file(_TIGER_URL)
    print(f"  {len(gdf)} tracts loaded")

    # Stable join key (11-digit GEOID) and human-readable display name.
    gdf["tract_geoid"] = gdf["GEOID"].astype(str).str.strip()
    gdf["tract_name"]  = "Tract " + gdf["NAME"].astype(str).str.strip()

    # Compute area in metric CRS; centroid in WGS84 (consistent with other freeze scripts).
    gdf_m = gdf.to_crs(_METRIC_CRS)
    gdf["area_km2"]     = (gdf_m.geometry.area / 1e6).round(4)
    gdf["centroid_lat"] = gdf.geometry.centroid.y.round(6)
    gdf["centroid_lng"] = gdf.geometry.centroid.x.round(6)

    # ── GeoJSON output ────────────────────────────────────────────────────────
    geo_out = gdf[["tract_geoid", "tract_name", "geometry"]].copy()
    GEO_OUT.parent.mkdir(parents=True, exist_ok=True)
    geo_out.to_file(GEO_OUT, driver="GeoJSON")
    print(f"  Wrote {GEO_OUT}")

    # ── Seed CSV output ───────────────────────────────────────────────────────
    seed = gdf[[
        "tract_geoid", "tract_name",
        "area_km2", "centroid_lat", "centroid_lng",
    ]].sort_values("tract_geoid").reset_index(drop=True)
    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    seed.to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(seed)} rows)")


if __name__ == "__main__":
    main()
