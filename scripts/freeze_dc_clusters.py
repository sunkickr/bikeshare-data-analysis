#!/usr/bin/env python3
"""Freeze DC Neighborhood Cluster polygons from DC Open Data into two outputs:

  data/geo/dc_clusters.geojson          — polygon file for the dashboard map
  bikeshare/seeds/dc_clusters.csv       — tabular metadata for dbt

Clusters are DC's official planning unit: 46 polygons grouping 2–5 individual
neighborhoods each. Source: DC Office of Planning via DC Open Data (CC BY 4.0).

Run this once to snapshot the boundaries. Re-run only when you want to
deliberately update the cluster definitions.

Usage:
    .venv/bin/python scripts/freeze_dc_clusters.py
"""
import json
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
GEO_OUT   = REPO_ROOT / "data" / "geo" / "dc_clusters.geojson"
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_clusters.csv"

_URL = (
    "https://opendata.dc.gov/api/download/v1/items/"
    "f6c703ebe2534fc3800609a07bad8f5b/geojson?layers=17"
)
_METRIC_CRS = 32618


def main() -> None:
    print("Downloading DC Neighborhood Cluster polygons from DC Open Data...")
    req = urllib.request.Request(_URL, headers={"User-Agent": "bikeshare-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.load(resp)

    gdf = gpd.GeoDataFrame.from_features(raw["features"], crs=4326)

    # Keep only original planning clusters (exclude the 7 gap-filler polygons).
    gdf = gdf[gdf["TYPE"] == "Original"].copy().reset_index(drop=True)
    print(f"  {len(gdf)} original planning clusters")

    # Compute area and centroid in metric CRS.
    gdf_m = gdf.to_crs(_METRIC_CRS)
    gdf["area_km2"]     = (gdf_m.geometry.area / 1e6).round(4)
    gdf["centroid_lat"] = gdf.geometry.centroid.y.round(6)
    gdf["centroid_lng"] = gdf.geometry.centroid.x.round(6)

    # Normalise display name: use NBH_NAMES (the readable neighbourhood list).
    # NAME ("Cluster 16") is the stable ID we use as the join key.
    gdf["cluster_id"]           = gdf["NAME"].str.strip()
    gdf["cluster_display_name"] = gdf["NBH_NAMES"].str.strip()

    # ── GeoJSON output ────────────────────────────────────────────────────────
    geo_out = gdf[["cluster_id", "cluster_display_name", "geometry"]].copy()
    GEO_OUT.parent.mkdir(parents=True, exist_ok=True)
    geo_out.to_file(GEO_OUT, driver="GeoJSON")
    print(f"  Wrote {GEO_OUT}")

    # ── Seed CSV output ───────────────────────────────────────────────────────
    seed = gdf[[
        "cluster_id", "cluster_display_name",
        "area_km2", "centroid_lat", "centroid_lng",
    ]].sort_values("cluster_id").reset_index(drop=True)
    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    seed.to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(seed)} rows)")


if __name__ == "__main__":
    main()
