#!/usr/bin/env python3
"""Freeze DC Census block group polygons from TIGER 2023 into two outputs:

  data/geo/dc_block_groups.geojson      — polygon file for the dashboard map
  bikeshare/seeds/dc_block_groups.csv   — tabular metadata for dbt

Block groups are the finest Census geography with ACS income/population data
(~450–500 in DC, roughly 2–5 per tract). Source: Census TIGER/Line 2023.

Run this once to snapshot the boundaries. Re-run only when updating TIGER vintage.

Usage:
    .venv/bin/python scripts/freeze_dc_block_groups.py
"""
from pathlib import Path

import geopandas as gpd

REPO_ROOT = Path(__file__).parent.parent
GEO_OUT   = REPO_ROOT / "data" / "geo" / "dc_block_groups.geojson"
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_block_groups.csv"

_TIGER_URL  = "https://www2.census.gov/geo/tiger/TIGER2023/BG/tl_2023_11_bg.zip"
_METRIC_CRS = 32618


def _format_tract(tractce: str) -> str:
    """Convert 6-digit TRACTCE to human-readable tract number.

    '001400' → '14.00', '001402' → '14.02', '000100' → '1.00'
    """
    return f"{int(tractce) / 100:.2f}"


def main() -> None:
    print("Downloading TIGER 2023 block group boundaries for DC...")
    gdf = gpd.read_file(_TIGER_URL)
    print(f"  {len(gdf)} block groups loaded")

    # Stable 12-digit GEOID and human-readable display name.
    gdf["bg_geoid"] = gdf["GEOID"].astype(str).str.strip()
    gdf["bg_name"]  = (
        "BG " + gdf["BLKGRPCE"].astype(str).str.strip()
        + ", Tract " + gdf["TRACTCE"].apply(_format_tract)
    )

    # Area in metric CRS; centroid in WGS84 (consistent with other freeze scripts).
    gdf_m = gdf.to_crs(_METRIC_CRS)
    gdf["area_km2"]     = (gdf_m.geometry.area / 1e6).round(4)
    gdf["centroid_lat"] = gdf.geometry.centroid.y.round(6)
    gdf["centroid_lng"] = gdf.geometry.centroid.x.round(6)

    # ── GeoJSON output ────────────────────────────────────────────────────────
    geo_out = gdf[["bg_geoid", "bg_name", "geometry"]].copy()
    GEO_OUT.parent.mkdir(parents=True, exist_ok=True)
    geo_out.to_file(GEO_OUT, driver="GeoJSON")
    print(f"  Wrote {GEO_OUT}")

    # ── Seed CSV output ───────────────────────────────────────────────────────
    seed = gdf[[
        "bg_geoid", "bg_name",
        "area_km2", "centroid_lat", "centroid_lng",
    ]].sort_values("bg_geoid").reset_index(drop=True)
    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    seed.to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(seed)} rows)")


if __name__ == "__main__":
    main()
