#!/usr/bin/env python3
"""Freeze DC neighbourhood polygons from OpenStreetMap into two outputs:

  data/geo/dc_neighborhoods_osm.geojson   — polygon file for the dashboard map
  bikeshare/seeds/dc_neighborhoods.csv    — tabular metadata for dbt

Run this once to snapshot the boundaries. Re-run only when you want to
deliberately update the neighbourhood definitions.

Usage:
    .venv/bin/python scripts/freeze_dc_neighborhoods.py
"""
import json
import warnings
from pathlib import Path

import geopandas as gpd
import osmnx as ox

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).parent.parent
GEO_OUT   = REPO_ROOT / "data" / "geo" / "dc_neighborhoods_osm.geojson"
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_neighborhoods.csv"

# UTM Zone 18N — appropriate metric CRS for Washington DC.
_METRIC_CRS = 32618


def main() -> None:
    print("Fetching DC neighbourhood polygons from OpenStreetMap...")
    gdf = ox.features_from_place(
        "Washington, DC, USA",
        tags={"place": "neighbourhood"},
    )

    # Keep only polygon features; point features are OSM label nodes.
    polys = gdf[gdf.geometry.geom_type == "Polygon"].copy()
    polys = polys.reset_index()
    print(f"  {len(polys)} polygon neighbourhoods found")

    # Readable name — drop any rows with no name at all.
    polys["neighborhood_name"] = polys["name"].fillna("").str.strip()
    polys = polys[polys["neighborhood_name"] != ""].copy()
    print(f"  {len(polys)} with readable names")

    # Compute area and centroid in metric CRS, then reproject back to WGS84.
    polys_m = polys.to_crs(_METRIC_CRS)
    polys["area_km2"]      = (polys_m.geometry.area / 1e6).round(4)
    polys["centroid_lat"]  = polys.geometry.centroid.y.round(6)
    polys["centroid_lng"]  = polys.geometry.centroid.x.round(6)
    polys["osm_id"]        = polys["id"].astype(str)

    # ── GeoJSON output (polygon geometry + name property) ────────────────────
    geo_out = polys[["neighborhood_name", "osm_id", "geometry"]].copy()
    geo_out = geo_out.to_crs(4326)  # ensure WGS84
    GEO_OUT.parent.mkdir(parents=True, exist_ok=True)
    geo_out.to_file(GEO_OUT, driver="GeoJSON")
    print(f"  Wrote {GEO_OUT}")

    # ── Seed CSV output (tabular metadata, no geometry) ──────────────────────
    seed = polys[["neighborhood_name", "osm_id", "area_km2", "centroid_lat", "centroid_lng"]]
    seed = seed.sort_values("neighborhood_name").reset_index(drop=True)
    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    seed.to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(seed)} rows)")


if __name__ == "__main__":
    main()
