"""City Comparison — 12 headline metrics rendered as paired DC/NYC tiles.

This page intentionally ignores the System filter: it is *the* place to look at
both systems side by side. The Month filter still applies (the comparison only
makes sense within a defined window).
"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from lib import queries
from lib.charts import (
    comparison_tile,
    empty_state,
    format_hours,
    format_int,
    format_minutes,
    format_pct,
)
from lib.filters import render_header_filters
from lib.theme import apply_plotly_defaults

st.set_page_config(page_title="City Comparison", page_icon="🚲", layout="wide")
apply_plotly_defaults()

ALL_SYSTEMS = ("capitalbikeshare", "citibike")


def main() -> None:
    st.title("City Comparison")
    filters = render_header_filters()

    if set(filters.systems) != set(ALL_SYSTEMS):
        st.info("This page always compares both systems — the System filter is ignored here.")

    st.divider()

    summary = queries.city_summary(ALL_SYSTEMS, filters.month_start, filters.month_end)
    if summary.empty:
        empty_state("No data for either system in this window.")
        return

    dc_row = _row_for(summary, "capitalbikeshare")
    nyc_row = _row_for(summary, "citibike")
    dc_metrics = _derive_metrics(dc_row)
    nyc_metrics = _derive_metrics(nyc_row)

    _render_grid(dc_metrics, nyc_metrics)


def _row_for(df: pd.DataFrame, system: str) -> pd.Series | None:
    sub = df[df["system"] == system]
    return sub.iloc[0] if not sub.empty else None


def _safe(row: pd.Series | None, key: str) -> Any:
    """Get a value from a row, returning None for missing/NaN."""
    if row is None:
        return None
    if key not in row.index:
        return None
    val = row[key]
    return None if pd.isna(val) else val


def _safe_div(a: Any, b: Any) -> float | None:
    if a is None or b is None:
        return None
    b = float(b)
    if b == 0:
        return None
    return float(a) / b


def _derive_metrics(row: pd.Series | None) -> dict[str, Any]:
    """Pull raw values + compute share/rate metrics that aren't in the SQL."""
    total = _safe(row, "total_rides")
    return {
        "total_rides": total,
        "total_hours": _safe(row, "total_hours"),
        "avg_daily_rides": _safe_div(total, _safe(row, "active_days")),
        "busiest_day_rides": _safe(row, "busiest_day_rides"),
        "unique_stations": _safe(row, "unique_stations"),
        "active_stations": _safe(row, "active_stations"),
        "rides_per_active_station": _safe_div(total, _safe(row, "active_stations")),
        "avg_minutes": _safe(row, "avg_minutes"),
        "member_share": _safe_div(_safe(row, "member_rides"), total),
        "classic_share": _safe_div(_safe(row, "classic_rides"), total),
        "night_owl_share": _safe_div(_safe(row, "night_owl_rides"), total),
        "round_trip_share": _safe_div(_safe(row, "round_trip_rides"), total),
    }


def _render_grid(dc: dict[str, Any], nyc: dict[str, Any]) -> None:
    """3 rows × 4 columns = 12 paired-bar comparison tiles, grouped by theme."""
    Metric = tuple[str, str, Callable[[Any], str]]
    rows: list[list[Metric]] = [
        # Volume
        [
            ("Total Rides", "total_rides", format_int),
            ("Total Hours", "total_hours", format_hours),
            ("Avg Daily Rides", "avg_daily_rides", format_int),
            ("Busiest Day Rides", "busiest_day_rides", format_int),
        ],
        # Network + duration
        [
            ("Unique Stations", "unique_stations", format_int),
            ("Active Stations", "active_stations", format_int),
            ("Rides / Active Station", "rides_per_active_station", format_int),
            ("Avg Ride Min", "avg_minutes", format_minutes),
        ],
        # Composition (shares)
        [
            ("Member Share", "member_share", format_pct),
            ("Classic Share", "classic_share", format_pct),
            ("Night Owl Share", "night_owl_share", format_pct),
            ("Round Trip Share", "round_trip_share", format_pct),
        ],
    ]

    for row in rows:
        cols = st.columns(4)
        for col, (label, key, fmt) in zip(cols, row):
            with col:
                comparison_tile(label, dc.get(key), nyc.get(key), format_fn=fmt)


main()
