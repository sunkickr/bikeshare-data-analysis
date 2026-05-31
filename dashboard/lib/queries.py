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
