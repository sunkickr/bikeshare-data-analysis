#!/usr/bin/env python3
"""Assign each Capital Bikeshare station within DC city limits to its
Neighborhood Cluster via point-in-polygon join, with nearest-polygon
fallback for stations that fall in gaps between cluster polygons.

Reads:
  data/geo/dc_clusters.geojson          — frozen cluster polygons
  analytics_marts.dim_stations          — station lat/lng from Postgres

Writes:
  bikeshare/seeds/dc_station_clusters.csv

Usage:
    .venv/bin/python scripts/assign_dc_stations_clusters.py
"""
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
import warnings
from sqlalchemy import create_engine, text

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).parent.parent
GEO_IN    = REPO_ROOT / "data" / "geo" / "dc_clusters.geojson"
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_station_clusters.csv"

_DB_URL = "postgresql://dbt_user:dbt_password@localhost:5432/bikeshare"
_CRS    = 4326
_METRIC = 32618


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


def main() -> None:
    print("Loading Capital Bikeshare stations from Postgres...")
    engine = create_engine(_DB_URL)
    all_stations = _load_stations(engine)
    dc_stations = _filter_to_dc(all_stations)
    print(f"  {len(dc_stations)} stations within DC city limits")

    print("Loading frozen cluster polygons...")
    clusters = gpd.read_file(GEO_IN)[["cluster_id", "geometry"]]
    print(f"  {len(clusters)} clusters")

    print("Point-in-polygon join...")
    joined = gpd.sjoin(dc_stations, clusters, how="left", predicate="within")
    assigned = joined[joined["cluster_id"].notna()][["station_id", "cluster_id"]]
    gaps     = dc_stations[dc_stations["station_id"].isin(
        joined[joined["cluster_id"].isna()]["station_id"]
    )]
    print(f"  {len(assigned)} assigned directly, {len(gaps)} in polygon gaps")

    if not gaps.empty:
        print("  Applying nearest-centroid fallback...")
        gaps_m    = gaps.to_crs(_METRIC)
        clusters_m = clusters.to_crs(_METRIC).copy()
        clusters_m["geometry"] = clusters_m.geometry.centroid
        fallback = gpd.sjoin_nearest(
            gaps_m, clusters_m[["cluster_id", "geometry"]], how="left"
        )[["station_id", "cluster_id"]].drop_duplicates("station_id")
        result = pd.concat([assigned, fallback], ignore_index=True)
    else:
        result = assigned

    result = result.drop_duplicates("station_id").sort_values("station_id")
    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(result)} rows)")

    print("\nStations per cluster (top 10):")
    print(result["cluster_id"].value_counts().head(10).to_string())


if __name__ == "__main__":
    main()
