#!/usr/bin/env python3
"""Assign each Capital Bikeshare station within DC city limits to its Census
block group via point-in-polygon join, with nearest-polygon fallback.

Reads:
  data/geo/dc_block_groups.geojson       — frozen block group polygons
  analytics_marts.dim_stations           — station lat/lng from Postgres

Writes:
  bikeshare/seeds/dc_station_block_groups.csv

Usage:
    .venv/bin/python scripts/assign_dc_stations_block_groups.py
"""
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
import warnings
from sqlalchemy import create_engine, text

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).parent.parent
GEO_IN    = REPO_ROOT / "data" / "geo" / "dc_block_groups.geojson"
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_station_block_groups.csv"

_DB_URL  = "postgresql://dbt_user:dbt_password@localhost:5432/bikeshare"
_CRS     = 4326
_METRIC  = 32618


def _load_stations(engine) -> gpd.GeoDataFrame:
    df = pd.read_sql(text("""
        SELECT station_id, station_name, lat, lng
        FROM analytics_marts.dim_stations
        WHERE system = 'capitalbikeshare'
          AND lat IS NOT NULL AND lng IS NOT NULL
    """), engine)
    return gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["lng"], df["lat"]),
        crs=_CRS,
    )


def _filter_to_dc(stations: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    print("  Fetching DC city boundary from OSM...")
    dc_boundary = ox.geocode_to_gdf("Washington, DC, USA")
    in_dc = gpd.sjoin(stations, dc_boundary[["geometry"]], how="inner", predicate="within")
    return in_dc[stations.columns].copy()


def _nearest_fallback(
    gaps: gpd.GeoDataFrame,
    block_groups: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Assign boundary stations to the nearest block group centroid."""
    gaps_m = gaps.to_crs(_METRIC)
    bgs_m  = block_groups.to_crs(_METRIC)
    centroids = bgs_m.copy()
    centroids["geometry"] = centroids.geometry.centroid

    nearest = gpd.sjoin_nearest(gaps_m, centroids[["bg_geoid", "geometry"]], how="left")
    return nearest[["station_id", "bg_geoid"]].drop_duplicates("station_id")


def main() -> None:
    print("Loading Capital Bikeshare stations from Postgres...")
    engine = create_engine(_DB_URL)
    all_stations = _load_stations(engine)
    print(f"  {len(all_stations)} total stations")

    dc_stations = _filter_to_dc(all_stations)
    print(f"  {len(dc_stations)} within DC city limits")

    print("Loading frozen block group polygons...")
    block_groups = gpd.read_file(GEO_IN)[["bg_geoid", "geometry"]]

    print("Point-in-polygon join...")
    joined   = gpd.sjoin(dc_stations, block_groups, how="left", predicate="within")
    assigned = joined[joined["bg_geoid"].notna()][["station_id", "bg_geoid"]]
    gaps     = dc_stations[dc_stations["station_id"].isin(
        joined[joined["bg_geoid"].isna()]["station_id"]
    )]
    print(f"  {len(assigned)} assigned directly, {len(gaps)} on boundaries")

    if not gaps.empty:
        print("  Applying nearest-centroid fallback for boundary stations...")
        fallback = _nearest_fallback(gaps, block_groups)
        result = pd.concat([assigned, fallback], ignore_index=True)
    else:
        result = assigned

    result = result.drop_duplicates("station_id").sort_values("station_id")
    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(result)} rows)")
    print()
    bg_counts = result["bg_geoid"].value_counts()
    print("Stations per block group (top 10):")
    print(bg_counts.head(10).to_string())


if __name__ == "__main__":
    main()
