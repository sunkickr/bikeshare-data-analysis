#!/usr/bin/env python3
"""Assign each Capital Bikeshare station within DC city limits to its Census
tract via point-in-polygon join, with nearest-polygon fallback for stations
that fall on tract boundaries.

Reads:
  data/geo/dc_census_tracts.geojson      — frozen tract polygons
  analytics_marts.dim_stations           — station lat/lng from Postgres

Writes:
  bikeshare/seeds/dc_station_census_tracts.csv

Methodology:
  1. Filter to stations inside DC city limits (excludes Arlington, Alexandria,
     and Maryland stations that are also part of the Capital Bikeshare network).
  2. Point-in-polygon join assigns stations that fall inside a tract polygon.
  3. For stations on boundaries, nearest-centroid fallback assigns them to the
     geographically closest tract.

Usage:
    .venv/bin/python scripts/assign_dc_stations_census_tracts.py
"""
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
import warnings
from sqlalchemy import create_engine, text

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).parent.parent
GEO_IN    = REPO_ROOT / "data" / "geo" / "dc_census_tracts.geojson"
SEED_OUT  = REPO_ROOT / "bikeshare" / "seeds" / "dc_station_census_tracts.csv"

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
    tracts: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Assign boundary stations to the nearest tract centroid."""
    gaps_m    = gaps.to_crs(_METRIC)
    tracts_m  = tracts.to_crs(_METRIC)
    centroids = tracts_m.copy()
    centroids["geometry"] = centroids.geometry.centroid

    nearest = gpd.sjoin_nearest(gaps_m, centroids[["tract_geoid", "geometry"]], how="left")
    return nearest[["station_id", "tract_geoid"]].drop_duplicates("station_id")


def main() -> None:
    print("Loading Capital Bikeshare stations from Postgres...")
    engine = create_engine(_DB_URL)
    all_stations = _load_stations(engine)
    print(f"  {len(all_stations)} total stations")

    dc_stations = _filter_to_dc(all_stations)
    print(f"  {len(dc_stations)} within DC city limits")

    print("Loading frozen tract polygons...")
    tracts = gpd.read_file(GEO_IN)[["tract_geoid", "geometry"]]

    print("Point-in-polygon join...")
    joined   = gpd.sjoin(dc_stations, tracts, how="left", predicate="within")
    assigned = joined[joined["tract_geoid"].notna()][["station_id", "tract_geoid"]]
    gaps     = dc_stations[dc_stations["station_id"].isin(
        joined[joined["tract_geoid"].isna()]["station_id"]
    )]
    print(f"  {len(assigned)} assigned directly, {len(gaps)} on boundaries")

    if not gaps.empty:
        print("  Applying nearest-centroid fallback for boundary stations...")
        fallback = _nearest_fallback(gaps, tracts)
        result = pd.concat([assigned, fallback], ignore_index=True)
    else:
        result = assigned

    result = result.drop_duplicates("station_id").sort_values("station_id")
    SEED_OUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(SEED_OUT, index=False)
    print(f"  Wrote {SEED_OUT} ({len(result)} rows)")
    print()
    tract_counts = result["tract_geoid"].value_counts()
    print("Stations per tract (top 10):")
    print(tract_counts.head(10).to_string())


if __name__ == "__main__":
    main()
