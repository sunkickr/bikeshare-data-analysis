"""All SQL the dashboard runs. Each function returns a pandas DataFrame and is
cached with @st.cache_data keyed on its arguments.

Pages should import functions from here, not write inline SQL. Keeping queries
in one module makes it easy to reason about cache invalidation and find slow ones.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from lib.db import run_query

_CACHE_TTL = 3600   # 1 hour — dbt refreshes weekly


@st.cache_data(ttl=_CACHE_TTL, show_spinner="Loading rides…")
def overview_kpis(systems: tuple[str, ...], month_start: date, month_end: date) -> pd.DataFrame:
    """One row per system in scope, with the top-level KPIs.

    Columns: system, total_rides, total_hours, member_rides, casual_rides,
    classic_rides, electric_rides.
    """
    sql = """
        SELECT
            system,
            SUM(total_rides)              AS total_rides,
            SUM(total_hours_on_bike)      AS total_hours,
            SUM(CASE WHEN member_casual = 'member' THEN total_rides ELSE 0 END) AS member_rides,
            SUM(CASE WHEN member_casual = 'casual' THEN total_rides ELSE 0 END) AS casual_rides,
            SUM(CASE WHEN rideable_type = 'classic_bike'  THEN total_rides ELSE 0 END) AS classic_rides,
            SUM(CASE WHEN rideable_type = 'electric_bike' THEN total_rides ELSE 0 END) AS electric_rides
        FROM analytics_marts.agg_rides_daily
        WHERE system = ANY(:systems)
          AND started_date >= :month_start
          AND started_date < (DATE :month_end + INTERVAL '1 month')
        GROUP BY system
        ORDER BY system
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def unique_station_count(systems: tuple[str, ...]) -> pd.DataFrame:
    """One row per system with its total distinct station count from dim_stations.

    Not month-filtered: dim_stations is a slowly-changing dimension, station counts
    reflect everything we've ever seen, which is the metric people expect on Overview.
    """
    sql = """
        SELECT system, COUNT(DISTINCT station_id) AS unique_stations
        FROM analytics_marts.dim_stations
        WHERE system = ANY(:systems)
        GROUP BY system
        ORDER BY system
    """
    return run_query(sql, {"systems": list(systems)})


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def member_casual_breakdown(systems: tuple[str, ...], month_start: date, month_end: date) -> pd.DataFrame:
    """One row per (system, member_casual) with total_rides over the filter window.

    Used by the Overview donut chart and any other member-vs-casual visualization.
    """
    sql = """
        SELECT system, member_casual, SUM(total_rides) AS total_rides
        FROM analytics_marts.agg_rides_daily
        WHERE system = ANY(:systems)
          AND started_date >= :month_start
          AND started_date < (DATE :month_end + INTERVAL '1 month')
        GROUP BY system, member_casual
        ORDER BY system, member_casual
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def rideable_type_breakdown(systems: tuple[str, ...], month_start: date, month_end: date) -> pd.DataFrame:
    """One row per (system, rideable_type) with total_rides over the filter window.

    Used by the Overview Classic-vs-Electric donut.
    """
    sql = """
        SELECT system, rideable_type, SUM(total_rides) AS total_rides
        FROM analytics_marts.agg_rides_daily
        WHERE system = ANY(:systems)
          AND started_date >= :month_start
          AND started_date < (DATE :month_end + INTERVAL '1 month')
        GROUP BY system, rideable_type
        ORDER BY system, rideable_type
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


# ── Phase 2: Ride Activity ──────────────────────────────────────────────────


@st.cache_data(ttl=_CACHE_TTL, show_spinner="Loading daily volume…")
def daily_rides_over_time(systems: tuple[str, ...], month_start: date, month_end: date) -> pd.DataFrame:
    """One row per (started_date, system). Drives the daily-rides line chart."""
    sql = """
        SELECT started_date, system, SUM(total_rides) AS total_rides
        FROM analytics_marts.agg_rides_daily
        WHERE system = ANY(:systems)
          AND started_date >= :month_start
          AND started_date < (DATE :month_end + INTERVAL '1 month')
        GROUP BY started_date, system
        ORDER BY started_date, system
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def duration_stats(systems: tuple[str, ...], month_start: date, month_end: date) -> pd.DataFrame:
    """Per system: rides-weighted average duration, max longest duration, and total
    rides + night-owl rides. Folds the daily mart across the filter window.

    Important: avg_minutes is weighted by total_rides because a simple AVG of
    avg_ride_minutes would mis-weight low-traffic days against high-traffic ones.
    """
    sql = """
        SELECT
            system,
            SUM(avg_ride_minutes * total_rides) / NULLIF(SUM(total_rides), 0) AS avg_minutes,
            MAX(longest_ride_minutes)                                          AS longest_minutes,
            SUM(total_rides)                                                   AS total_rides,
            SUM(night_owl_rides)                                               AS night_owl_rides
        FROM analytics_marts.agg_rides_daily
        WHERE system = ANY(:systems)
          AND started_date >= :month_start
          AND started_date < (DATE :month_end + INTERVAL '1 month')
        GROUP BY system
        ORDER BY system
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


@st.cache_data(ttl=_CACHE_TTL, show_spinner="Scanning fct_rides for shortest trip…")
def shortest_ride_between_stations(systems: tuple[str, ...], month_start: date, month_end: date) -> pd.DataFrame:
    """Per system: shortest non-zero ride that started and ended at *different*
    stations. Only query in the dashboard that hits fct_rides directly — the
    is_between_stations flag exists per ride and the daily mart has collapsed it.

    Filters duration_minutes > 0 to exclude data-quality artifacts (rides with
    zero or negative durations sneak in from upstream feeds).
    """
    # No ::timestamp casts: Postgres implicitly converts the :month_* date params
    # to timestamps when comparing against fct_rides.started_at, and SQLAlchemy's
    # text() parameter parser doesn't like `:name::type` (the `::` collides with
    # its `:name` bind-parameter syntax).
    sql = """
        SELECT system, MIN(duration_minutes) AS shortest_minutes
        FROM analytics_marts.fct_rides
        WHERE system = ANY(:systems)
          AND is_between_stations
          AND duration_minutes > 0
          AND started_at >= :month_start
          AND started_at < (DATE :month_end + INTERVAL '1 month')
        GROUP BY system
        ORDER BY system
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def busiest_and_quietest_day(systems: tuple[str, ...], month_start: date, month_end: date) -> pd.DataFrame:
    """For each system, the single date with the most rides and the date with the
    fewest. Returns long-format: (system, kind, started_date, rides) where kind is
    'busiest' or 'quietest'. Ties broken arbitrarily by ROW_NUMBER.
    """
    sql = """
        WITH daily AS (
            SELECT system, started_date, SUM(total_rides) AS rides
            FROM analytics_marts.agg_rides_daily
            WHERE system = ANY(:systems)
              AND started_date >= :month_start
              AND started_date < (DATE :month_end + INTERVAL '1 month')
            GROUP BY system, started_date
        ),
        ranked AS (
            SELECT
                system,
                started_date,
                rides,
                ROW_NUMBER() OVER (PARTITION BY system ORDER BY rides DESC, started_date) AS rank_busy,
                ROW_NUMBER() OVER (PARTITION BY system ORDER BY rides ASC,  started_date) AS rank_quiet
            FROM daily
        )
        SELECT system, 'busiest'  AS kind, started_date, rides FROM ranked WHERE rank_busy  = 1
        UNION ALL
        SELECT system, 'quietest' AS kind, started_date, rides FROM ranked WHERE rank_quiet = 1
        ORDER BY system, kind
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def daily_member_casual(systems: tuple[str, ...], month_start: date, month_end: date) -> pd.DataFrame:
    """One row per (started_date, system, member_casual). Stacked-bar timeseries."""
    sql = """
        SELECT started_date, system, member_casual, SUM(total_rides) AS total_rides
        FROM analytics_marts.agg_rides_daily
        WHERE system = ANY(:systems)
          AND started_date >= :month_start
          AND started_date < (DATE :month_end + INTERVAL '1 month')
        GROUP BY started_date, system, member_casual
        ORDER BY started_date, system, member_casual
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def daily_rideable_type(systems: tuple[str, ...], month_start: date, month_end: date) -> pd.DataFrame:
    """One row per (started_date, system, rideable_type). Stacked-bar timeseries."""
    sql = """
        SELECT started_date, system, rideable_type, SUM(total_rides) AS total_rides
        FROM analytics_marts.agg_rides_daily
        WHERE system = ANY(:systems)
          AND started_date >= :month_start
          AND started_date < (DATE :month_end + INTERVAL '1 month')
        GROUP BY started_date, system, rideable_type
        ORDER BY started_date, system, rideable_type
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


# ── Phase 3: Stations & Routes ──────────────────────────────────────────────


@st.cache_data(ttl=_CACHE_TTL, show_spinner="Ranking stations…")
def top_start_stations(
    systems: tuple[str, ...], month_start: date, month_end: date, limit: int = 10
) -> pd.DataFrame:
    """Top N start stations per system, with ride counts, for the filter window.

    Uses ROW_NUMBER over fct_rides instead of two LIMIT queries — one round trip,
    deterministic tiebreak, and the result already comes back ranked.
    """
    sql = """
        WITH counts AS (
            SELECT system, start_station_name AS station_name, COUNT(*) AS rides
            FROM analytics_marts.fct_rides
            WHERE system = ANY(:systems)
              AND started_month BETWEEN :month_start AND :month_end
              AND start_station_name IS NOT NULL
            GROUP BY system, start_station_name
        ),
        ranked AS (
            SELECT
                system, station_name, rides,
                ROW_NUMBER() OVER (PARTITION BY system ORDER BY rides DESC, station_name) AS rank
            FROM counts
        )
        SELECT system, station_name, rides, rank
        FROM ranked
        WHERE rank <= :limit
        ORDER BY system, rank
    """
    return run_query(
        sql,
        {"systems": list(systems), "month_start": month_start, "month_end": month_end, "limit": limit},
    )


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def top_end_stations(
    systems: tuple[str, ...], month_start: date, month_end: date, limit: int = 10
) -> pd.DataFrame:
    """Top N end stations per system. Symmetric to top_start_stations on end_station_name."""
    sql = """
        WITH counts AS (
            SELECT system, end_station_name AS station_name, COUNT(*) AS rides
            FROM analytics_marts.fct_rides
            WHERE system = ANY(:systems)
              AND started_month BETWEEN :month_start AND :month_end
              AND end_station_name IS NOT NULL
            GROUP BY system, end_station_name
        ),
        ranked AS (
            SELECT
                system, station_name, rides,
                ROW_NUMBER() OVER (PARTITION BY system ORDER BY rides DESC, station_name) AS rank
            FROM counts
        )
        SELECT system, station_name, rides, rank
        FROM ranked
        WHERE rank <= :limit
        ORDER BY system, rank
    """
    return run_query(
        sql,
        {"systems": list(systems), "month_start": month_start, "month_end": month_end, "limit": limit},
    )


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def top_routes(
    systems: tuple[str, ...], month_start: date, month_end: date, limit: int = 5
) -> pd.DataFrame:
    """Top N (start_station, end_station) pairs per system, EXCLUDING round trips.

    Returns a `route_label` column ("Start → End") ready to use as a chart axis label.
    Round trips (start = end) are excluded — they represent hub stations rather
    than directional travel patterns, and they make the bar chart's top-N dominated
    by a few popular stations.
    """
    sql = """
        WITH counts AS (
            SELECT
                system,
                start_station_name,
                end_station_name,
                COUNT(*) AS rides
            FROM analytics_marts.fct_rides
            WHERE system = ANY(:systems)
              AND started_month BETWEEN :month_start AND :month_end
              AND start_station_name IS NOT NULL
              AND end_station_name IS NOT NULL
              AND start_station_name <> end_station_name
            GROUP BY system, start_station_name, end_station_name
        ),
        ranked AS (
            SELECT
                system, start_station_name, end_station_name, rides,
                ROW_NUMBER() OVER (
                    PARTITION BY system
                    ORDER BY rides DESC, start_station_name, end_station_name
                ) AS rank
            FROM counts
        )
        SELECT
            system, start_station_name, end_station_name, rides, rank,
            start_station_name || ' → ' || end_station_name AS route_label
        FROM ranked
        WHERE rank <= :limit
        ORDER BY system, rank
    """
    return run_query(
        sql,
        {"systems": list(systems), "month_start": month_start, "month_end": month_end, "limit": limit},
    )


# ── Stations & Routes map (geo-enriched) ───────────────────────────────────


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def all_stations_geo(systems: tuple[str, ...]) -> pd.DataFrame:
    """Every known station per system with its canonical lat/lng from dim_stations.

    Not month-filtered — the station *network* is a slowly-changing dimension and
    the map's dim background layer should be stable as users scrub through months.
    Cache key is just `systems`, so every filter combination on the page reuses
    this DataFrame for the background dots.
    """
    sql = """
        SELECT system, station_id, station_name, lat, lng
        FROM analytics_marts.dim_stations
        WHERE system = ANY(:systems)
          AND lat IS NOT NULL
          AND lng IS NOT NULL
        ORDER BY system, station_id
    """
    return run_query(sql, {"systems": list(systems)})


# Centroid coordinates per (system, station_name). Used by all three top_*_geo
# queries so the map matches the bar charts' name-based ranking even when a single
# station name has multiple station_ids in dim_stations (e.g., from a relocation).
# Defined as a SQL fragment so the same logic is reused in three queries.
_STATION_COORDS_CTE = """
    station_coords AS (
        SELECT system, station_name, AVG(lat) AS lat, AVG(lng) AS lng
        FROM analytics_marts.dim_stations
        WHERE lat IS NOT NULL AND lng IS NOT NULL
        GROUP BY system, station_name
    )
"""


@st.cache_data(ttl=_CACHE_TTL, show_spinner="Ranking stations…")
def top_start_stations_geo(
    systems: tuple[str, ...], month_start: date, month_end: date, limit: int = 10
) -> pd.DataFrame:
    """Top N start stations per system with lat/lng. Ranks by *name* to match
    the bar chart's top_start_stations query exactly. Coordinates are the
    centroid of all dim_stations rows sharing that name (handles the
    multiple-ids-per-name case from station relocations).
    """
    sql = f"""
        WITH counts AS (
            SELECT system, start_station_name AS station_name, COUNT(*) AS rides
            FROM analytics_marts.fct_rides
            WHERE system = ANY(:systems)
              AND started_month BETWEEN :month_start AND :month_end
              AND start_station_name IS NOT NULL
            GROUP BY system, start_station_name
        ),
        ranked AS (
            SELECT
                system, station_name, rides,
                ROW_NUMBER() OVER (PARTITION BY system ORDER BY rides DESC, station_name) AS rank
            FROM counts
        ),
        {_STATION_COORDS_CTE}
        SELECT
            r.system, r.station_name, r.rides, r.rank,
            sc.lat, sc.lng
        FROM ranked r
        LEFT JOIN station_coords sc
            ON sc.system = r.system AND sc.station_name = r.station_name
        WHERE r.rank <= :limit
        ORDER BY r.system, r.rank
    """
    return run_query(
        sql,
        {"systems": list(systems), "month_start": month_start, "month_end": month_end, "limit": limit},
    )


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def top_end_stations_geo(
    systems: tuple[str, ...], month_start: date, month_end: date, limit: int = 10
) -> pd.DataFrame:
    """Top N end stations per system with lat/lng. Symmetric to top_start_stations_geo.
    Ranks by name to match the top_end_stations bar chart query exactly.
    """
    sql = f"""
        WITH counts AS (
            SELECT system, end_station_name AS station_name, COUNT(*) AS rides
            FROM analytics_marts.fct_rides
            WHERE system = ANY(:systems)
              AND started_month BETWEEN :month_start AND :month_end
              AND end_station_name IS NOT NULL
            GROUP BY system, end_station_name
        ),
        ranked AS (
            SELECT
                system, station_name, rides,
                ROW_NUMBER() OVER (PARTITION BY system ORDER BY rides DESC, station_name) AS rank
            FROM counts
        ),
        {_STATION_COORDS_CTE}
        SELECT
            r.system, r.station_name, r.rides, r.rank,
            sc.lat, sc.lng
        FROM ranked r
        LEFT JOIN station_coords sc
            ON sc.system = r.system AND sc.station_name = r.station_name
        WHERE r.rank <= :limit
        ORDER BY r.system, r.rank
    """
    return run_query(
        sql,
        {"systems": list(systems), "month_start": month_start, "month_end": month_end, "limit": limit},
    )


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def top_routes_geo(
    systems: tuple[str, ...], month_start: date, month_end: date, limit: int = 5
) -> pd.DataFrame:
    """Top N routes per system with start AND end lat/lng. Ranks by name pair
    (matching the top_routes bar chart query) and excludes round trips. Both
    coordinate joins use the station_coords centroid CTE so the map and the
    bar chart always show the same top N.
    """
    sql = f"""
        WITH counts AS (
            SELECT
                system,
                start_station_name,
                end_station_name,
                COUNT(*) AS rides
            FROM analytics_marts.fct_rides
            WHERE system = ANY(:systems)
              AND started_month BETWEEN :month_start AND :month_end
              AND start_station_name IS NOT NULL
              AND end_station_name   IS NOT NULL
              AND start_station_name <> end_station_name
            GROUP BY system, start_station_name, end_station_name
        ),
        ranked AS (
            SELECT
                system, start_station_name, end_station_name, rides,
                ROW_NUMBER() OVER (
                    PARTITION BY system
                    ORDER BY rides DESC, start_station_name, end_station_name
                ) AS rank
            FROM counts
        ),
        {_STATION_COORDS_CTE}
        SELECT
            r.system, r.start_station_name, r.end_station_name, r.rides, r.rank,
            r.start_station_name || ' → ' || r.end_station_name AS route_label,
            ss.lat AS start_lat, ss.lng AS start_lng,
            es.lat AS end_lat,   es.lng AS end_lng
        FROM ranked r
        LEFT JOIN station_coords ss
            ON ss.system = r.system AND ss.station_name = r.start_station_name
        LEFT JOIN station_coords es
            ON es.system = r.system AND es.station_name = r.end_station_name
        WHERE r.rank <= :limit
        ORDER BY r.system, r.rank
    """
    return run_query(
        sql,
        {"systems": list(systems), "month_start": month_start, "month_end": month_end, "limit": limit},
    )


# ── Phase 4: Time Patterns + City Comparison ────────────────────────────────


@st.cache_data(ttl=_CACHE_TTL, show_spinner="Bucketing by hour…")
def rides_by_hour(
    systems: tuple[str, ...], month_start: date, month_end: date
) -> pd.DataFrame:
    """24 rows per system: ride count grouped by started_hour (0-23).

    Hits fct_rides because started_hour is a row-level column the daily mart
    rolled up. Filter on started_month so we hit the month-range index.
    """
    sql = """
        SELECT system, started_hour, COUNT(*) AS rides
        FROM analytics_marts.fct_rides
        WHERE system = ANY(:systems)
          AND started_month BETWEEN :month_start AND :month_end
        GROUP BY system, started_hour
        ORDER BY system, started_hour
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def rides_by_dow(
    systems: tuple[str, ...], month_start: date, month_end: date
) -> pd.DataFrame:
    """7 rows per system: rides by day of week with human-readable names. Ordered
    by started_dow so the dbt model's day-numbering convention drives the x-axis.
    """
    sql = """
        SELECT system, started_dow, started_dow_name, COUNT(*) AS rides
        FROM analytics_marts.fct_rides
        WHERE system = ANY(:systems)
          AND started_month BETWEEN :month_start AND :month_end
        GROUP BY system, started_dow, started_dow_name
        ORDER BY system, started_dow
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


@st.cache_data(ttl=_CACHE_TTL, show_spinner="Computing city comparison…")
def city_summary(
    systems: tuple[str, ...], month_start: date, month_end: date
) -> pd.DataFrame:
    """One row per system with every metric the City Comparison page needs.

    Three CTEs joined:
      - `daily` rolls agg_rides_daily up to one row per (system, started_date)
      - `agg` aggregates that to one row per system (with weighted avg minutes
        and busiest day count)
      - `stations` is the all-time unique-station count from dim_stations
      - `active` is the in-period active-station count from fct_rides
    """
    sql = """
        WITH daily AS (
            SELECT
                system,
                started_date,
                SUM(total_rides)                                                            AS rides,
                SUM(total_hours_on_bike)                                                    AS hours,
                SUM(avg_ride_minutes * total_rides)                                         AS weighted_min_sum,
                SUM(CASE WHEN member_casual = 'member'       THEN total_rides ELSE 0 END)   AS member_rides,
                SUM(CASE WHEN rideable_type = 'classic_bike' THEN total_rides ELSE 0 END)   AS classic_rides,
                SUM(night_owl_rides)                                                        AS night_owl_rides,
                SUM(round_trip_rides)                                                       AS round_trip_rides
            FROM analytics_marts.agg_rides_daily
            WHERE system = ANY(:systems)
              AND started_date >= :month_start
              AND started_date < (DATE :month_end + INTERVAL '1 month')
            GROUP BY system, started_date
        ),
        agg AS (
            SELECT
                system,
                SUM(rides)                                          AS total_rides,
                SUM(hours)                                          AS total_hours,
                SUM(weighted_min_sum) / NULLIF(SUM(rides), 0)       AS avg_minutes,
                SUM(member_rides)                                   AS member_rides,
                SUM(classic_rides)                                  AS classic_rides,
                SUM(night_owl_rides)                                AS night_owl_rides,
                SUM(round_trip_rides)                               AS round_trip_rides,
                COUNT(*)                                            AS active_days,
                MAX(rides)                                          AS busiest_day_rides
            FROM daily
            GROUP BY system
        ),
        stations AS (
            SELECT system, COUNT(DISTINCT station_id) AS unique_stations
            FROM analytics_marts.dim_stations
            WHERE system = ANY(:systems)
            GROUP BY system
        ),
        active AS (
            SELECT system, COUNT(DISTINCT start_station_id) AS active_stations
            FROM analytics_marts.fct_rides
            WHERE system = ANY(:systems)
              AND started_month BETWEEN :month_start AND :month_end
              AND start_station_id IS NOT NULL
            GROUP BY system
        )
        SELECT
            a.system,
            a.total_rides,
            a.total_hours,
            a.avg_minutes,
            a.member_rides,
            a.classic_rides,
            a.night_owl_rides,
            a.round_trip_rides,
            a.active_days,
            a.busiest_day_rides,
            s.unique_stations,
            ac.active_stations
        FROM agg a
        LEFT JOIN stations s  ON s.system  = a.system
        LEFT JOIN active   ac ON ac.system = a.system
        ORDER BY a.system
    """
    return run_query(sql, {"systems": list(systems), "month_start": month_start, "month_end": month_end})


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def neighborhood_rankings(min_population: int = 0, min_rides: int = 100) -> pd.DataFrame:
    """Eligible DC OSM neighborhoods for the latest month, one row each, with all
    eight ranking metrics plus the centroid (for map centering) and a `month`
    column for the page caption.

    DC-only: reads analytics_marts.agg_rides_by_neighborhood, which is unique per
    (neighborhood_name, started_month), so a single-month filter yields one row per
    neighborhood — no GROUP BY needed (unlike page 10's multi-month _load_data).

    "Latest month" is resolved in-SQL via MAX(started_month) so the page always
    reflects the freshest dbt run with no hardcoded date.

    Eligibility floor: strictly more than `min_rides` rides in the month, AND —
    only when `min_population > 0` — more than `min_population` residents. The
    population floor defaults OFF; raising it guards the rides_per_resident
    ranking from tiny-population zones with absurd per-capita ratios.
    """
    sql = """
        SELECT
            neighborhood_name,
            started_month                                                    AS month,
            total_rides,
            population,
            centroid_lat,
            centroid_lng,
            ROUND(member_rides    * 100.0 / NULLIF(total_rides, 0), 1)        AS member_pct,
            ROUND(electric_rides  * 100.0 / NULLIF(total_rides, 0), 1)        AS electric_pct,
            ROUND(round_trip_rides * 100.0 / NULLIF(total_rides, 0), 1)       AS round_trip_pct,
            ROUND(night_owl_rides * 100.0 / NULLIF(total_rides, 0), 1)        AS night_owl_pct,
            ROUND(total_rides::numeric / NULLIF(population, 0), 3)            AS rides_per_resident,
            ROUND(total_rides::numeric / NULLIF(station_count, 0), 1)         AS rides_per_station,
            ROUND(total_rides / NULLIF(area_km2, 0), 1)                       AS rides_per_km2
        FROM analytics_marts.agg_rides_by_neighborhood
        WHERE started_month = (
            SELECT MAX(started_month) FROM analytics_marts.agg_rides_by_neighborhood
        )
          AND total_rides > :min_rides
          AND (:min_population <= 0 OR population > :min_population)
        ORDER BY total_rides DESC
    """
    return run_query(sql, {"min_population": min_population, "min_rides": min_rides})
