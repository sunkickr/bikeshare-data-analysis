#!/usr/bin/env python3
"""Assign each Capital Bikeshare station within DC city limits to its OSM
neighbourhood via point-in-polygon join, with nearest-polygon fallback for
stations that fall in gaps between OSM polygons.

Reads:
  data/geo/dc_neighborhoods_osm.geojson  — frozen neighbourhood polygons
  analytics_marts.dim_stations           — station lat/lng from Postgres

Writes:
  bikeshare/seeds/dc_station_neighborhoods.csv

Methodology:
  1. Filter to stations inside DC city limits (excludes Arlington, Alexandria,
     and Maryland stations that are also part of the Capital Bikeshare network).
  2. Point-in-polygon join assigns stations that fall inside an OSM polygon.
  3. For the ~120 stations in gaps between polygons, nearest-centroid fallback
     assigns them to the geographically closest neighbourhood.

Usage:
    .venv/bin/python scripts/assign_dc_stations_neighborhoods.py
"""
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
import warnings
from sqlalchemy import create_engine, text

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).parent.parent
GEO_IN    = REPO_ROOT / "data" / "geo" / "dc_neighborhoods_osm.geojson"
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_station_neighborhoods.csv"

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
    nbhds: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Assign gap stations to the nearest neighbourhood centroid."""
    gaps_m   = gaps.to_crs(_METRIC)
    nbhds_m  = nbhds.to_crs(_METRIC)
    centroids = nbhds_m.copy()
    centroids["geometry"] = centroids.geometry.centroid

    nearest = gpd.sjoin_nearest(gaps_m, centroids[["neighborhood_name", "geometry"]], how="left")
    return nearest[["station_id", "neighborhood_name"]].drop_duplicates("station_id")


def main() -> None:
    print("Loading Capital Bikeshare stations from Postgres...")
    engine = create_engine(_DB_URL)
    all_stations = _load_stations(engine)
    print(f"  {len(all_stations)} total stations")

    dc_stations = _filter_to_dc(all_stations)
    print(f"  {len(dc_stations)} within DC city limits")

    print("Loading frozen neighbourhood polygons...")
    nbhds = gpd.read_file(GEO_IN)[["neighborhood_name", "geometry"]]

    print("Point-in-polygon join...")
    joined = gpd.sjoin(dc_stations, nbhds, how="left", predicate="within")
    assigned = joined[joined["neighborhood_name"].notna()][["station_id", "neighborhood_name"]]
    gaps     = dc_stations[dc_stations["station_id"].isin(
        joined[joined["neighborhood_name"].isna()]["station_id"]
    )]
    print(f"  {len(assigned)} assigned directly, {len(gaps)} in polygon gaps")

    if not gaps.empty:
        print("  Applying nearest-centroid fallback for gap stations...")
        fallback = _nearest_fallback(gaps, nbhds)
        result = pd.concat([assigned, fallback], ignore_index=True)
    else:
        result = assigned

    result = result.drop_duplicates("station_id").sort_values("station_id")
    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(result)} rows)")
    print()
    nbhd_counts = result["neighborhood_name"].value_counts()
    print("Stations per neighbourhood (top 10):")
    print(nbhd_counts.head(10).to_string())


if __name__ == "__main__":
    main()
