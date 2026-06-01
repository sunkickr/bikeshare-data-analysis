"""Stations & Routes — top start/end stations and top routes per system, all
ranked from `fct_rides` directly.

Single-system filter collapses the two-column layout to one. Round trips are
included in the top-routes list because they're informative — many of the most
popular pairs are people circling back to the same hub station.
"""
from __future__ import annotations

import streamlit as st

from lib import queries
from lib.charts import (
    empty_state,
    horizontal_bar_chart,
    station_route_map,
    system_columns,
    system_header,
)
from lib.filters import Filters, render_header_filters
from lib.theme import SYSTEM_COLOR, SYSTEM_LABEL, apply_plotly_defaults

st.set_page_config(page_title="Stations & Routes", page_icon="🚲", layout="wide")
apply_plotly_defaults()


def main() -> None:
    st.title("Stations & Routes")
    filters = render_header_filters()
    st.divider()

    _section_map(filters)
    st.divider()
    _section_top_stations("Top 10 start stations", queries.top_start_stations, filters)
    st.divider()
    _section_top_stations("Top 10 end stations", queries.top_end_stations, filters)
    st.divider()
    _section_top_routes(filters)


def _section_map(filters: Filters) -> None:
    """One Plotly mapbox map per system. Dim background = every station in the
    network; mint = top 10 start stations; orange = top 10 end stations; lines
    = top 5 routes. Layout uses `system_columns` so the row collapses to one
    full-width map when the user filters to a single system.
    """
    st.subheader("Top stations and routes")
    st.caption(
        "Dim dots = every station in the network · "
        "Mint = top 10 start stations · "
        "Orange = top 10 end stations · "
        "Lines = top 5 routes (width ∝ rides)."
    )

    all_df = queries.all_stations_geo(filters.systems)
    start_df = queries.top_start_stations_geo(filters.systems, filters.month_start, filters.month_end, limit=10)
    end_df = queries.top_end_stations_geo(filters.systems, filters.month_start, filters.month_end, limit=10)
    routes_df = queries.top_routes_geo(filters.systems, filters.month_start, filters.month_end, limit=5)

    if all_df.empty and start_df.empty and end_df.empty and routes_df.empty:
        empty_state()
        return

    cols, syss = system_columns(filters.systems)
    for col, system in zip(cols, syss):
        with col:
            system_header(system)
            sys_all = all_df[all_df["system"] == system]
            sys_start = start_df[start_df["system"] == system]
            sys_end = end_df[end_df["system"] == system]
            sys_routes = routes_df[routes_df["system"] == system]
            if sys_all.empty and sys_start.empty and sys_end.empty and sys_routes.empty:
                empty_state(f"No map data for {SYSTEM_LABEL[system]}.")
                continue
            fig = station_route_map(
                sys_all, sys_start, sys_end, sys_routes,
                system=system,
                height=460,
            )
            st.plotly_chart(fig, use_container_width=True)


def _section_top_stations(title: str, query_fn, filters: Filters) -> None:
    """Render two horizontal bar charts side by side, one per system, of the
    top-10 stations (start or end) by ride count.
    """
    st.subheader(title)
    df = query_fn(filters.systems, filters.month_start, filters.month_end, limit=10)
    if df.empty:
        empty_state()
        return

    cols, syss = system_columns(filters.systems)
    for col, system in zip(cols, syss):
        with col:
            system_header(system)
            sub = df[df["system"] == system]
            if sub.empty:
                empty_state(f"No station data for {SYSTEM_LABEL[system]}.")
                continue
            fig = horizontal_bar_chart(
                sub,
                label_col="station_name",
                value_col="rides",
                color=SYSTEM_COLOR[system],
                height=380,
            )
            st.plotly_chart(fig, use_container_width=True)


def _section_top_routes(filters: Filters) -> None:
    """Top 5 routes per system, labeled as 'Start Station → End Station'."""
    st.subheader("Top 5 routes")
    st.caption("Round trips (same station, start → end) are included.")
    df = queries.top_routes(filters.systems, filters.month_start, filters.month_end, limit=5)
    if df.empty:
        empty_state()
        return

    cols, syss = system_columns(filters.systems)
    for col, system in zip(cols, syss):
        with col:
            system_header(system)
            sub = df[df["system"] == system]
            if sub.empty:
                empty_state(f"No route data for {SYSTEM_LABEL[system]}.")
                continue
            fig = horizontal_bar_chart(
                sub,
                label_col="route_label",
                value_col="rides",
                color=SYSTEM_COLOR[system],
                height=260,
            )
            st.plotly_chart(fig, use_container_width=True)


main()
