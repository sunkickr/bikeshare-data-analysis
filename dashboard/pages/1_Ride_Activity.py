"""Ride Activity — daily volume, ride durations, member/casual + classic/electric
splits over time, and busiest/quietest days.

Filter window applies to every chart on this page. Single-system filter collapses
the two-column layout to one.
"""
from __future__ import annotations

import streamlit as st

from lib import queries
from lib.charts import (
    empty_state,
    format_int,
    format_minutes,
    kpi_tile,
    multi_system_line_chart,
    stacked_bar_timeseries,
    system_columns,
    system_header,
)
from lib.filters import Filters, render_header_filters
from lib.theme import SYSTEM_COLOR, SYSTEM_LABEL, apply_plotly_defaults

st.set_page_config(page_title="Ride Activity", page_icon="🚲", layout="wide")
apply_plotly_defaults()


def main() -> None:
    st.title("Ride Activity")
    filters = render_header_filters()
    st.divider()

    _section_daily_volume(filters)
    st.divider()
    _section_trip_stats(filters)
    st.divider()
    _section_composition(filters)


def _section_daily_volume(filters: Filters) -> None:
    """Single line chart with one line per system. Both systems share the time axis."""
    st.subheader("Daily rides")
    df = queries.daily_rides_over_time(filters.systems, filters.month_start, filters.month_end)
    if df.empty:
        empty_state()
        return
    fig = multi_system_line_chart(df, x_col="started_date", y_col="total_rides", y_title="Rides")
    st.plotly_chart(fig, use_container_width=True)


def _section_trip_stats(filters: Filters) -> None:
    """Two rows of three KPI tiles per system: duration metrics, then activity callouts."""
    st.subheader("Trip statistics")

    durations = queries.duration_stats(filters.systems, filters.month_start, filters.month_end)
    shortest = queries.shortest_ride_between_stations(filters.systems, filters.month_start, filters.month_end)
    busy = queries.busiest_and_quietest_day(filters.systems, filters.month_start, filters.month_end)

    if durations.empty:
        empty_state()
        return

    dur_by_sys = {row["system"]: row for _, row in durations.iterrows()}
    short_by_sys = {row["system"]: row["shortest_minutes"] for _, row in shortest.iterrows()}
    busy_by_sys = {
        (row["system"], row["kind"]): row for _, row in busy.iterrows()
    }

    cols, syss = system_columns(filters.systems)
    for col, system in zip(cols, syss):
        with col:
            system_header(system)
            row = dur_by_sys.get(system)
            if row is None:
                empty_state(f"No rides for {SYSTEM_LABEL[system]} in this window.")
                continue
            _render_system_kpis(
                accent=SYSTEM_COLOR[system],
                avg_min=row["avg_minutes"],
                longest_min=row["longest_minutes"],
                shortest_min=short_by_sys.get(system),
                total_rides=row["total_rides"],
                night_owl_rides=row["night_owl_rides"],
                busiest=busy_by_sys.get((system, "busiest")),
                quietest=busy_by_sys.get((system, "quietest")),
            )


def _render_system_kpis(
    *,
    accent: str,
    avg_min,
    longest_min,
    shortest_min,
    total_rides,
    night_owl_rides,
    busiest,
    quietest,
) -> None:
    """Two rows of three tiles. First row = durations, second row = activity callouts."""
    # Row 1: duration metrics
    r1 = st.columns(3)
    with r1[0]:
        kpi_tile("Avg Ride", format_minutes(float(avg_min) if avg_min is not None else None), accent=accent)
    with r1[1]:
        kpi_tile("Longest Ride", format_minutes(float(longest_min) if longest_min is not None else None), accent=accent)
    with r1[2]:
        kpi_tile(
            "Shortest (Different Stations)",
            format_minutes(float(shortest_min) if shortest_min is not None else None),
            accent=accent,
        )

    # Row 2: activity callouts
    r2 = st.columns(3)
    with r2[0]:
        if total_rides and total_rides > 0:
            share = float(night_owl_rides) / float(total_rides)
            kpi_tile("Night Owls (12–5am)", format_int(night_owl_rides), accent=accent, caption=f"{share:.1%} of rides")
        else:
            kpi_tile("Night Owls (12–5am)", "—", accent=accent)
    with r2[1]:
        if busiest is not None:
            kpi_tile(
                "Busiest Day",
                busiest["started_date"].strftime("%b %d"),
                accent=accent,
                caption=f"{format_int(busiest['rides'])} rides",
            )
        else:
            kpi_tile("Busiest Day", "—", accent=accent)
    with r2[2]:
        if quietest is not None:
            kpi_tile(
                "Quietest Day",
                quietest["started_date"].strftime("%b %d"),
                accent=accent,
                caption=f"{format_int(quietest['rides'])} rides",
            )
        else:
            kpi_tile("Quietest Day", "—", accent=accent)


def _section_composition(filters: Filters) -> None:
    """Two stacked-bar timeseries, side by side per system: member/casual and classic/electric."""
    st.subheader("Member vs Casual over time")
    df_member = queries.daily_member_casual(filters.systems, filters.month_start, filters.month_end)
    _render_stacked_panels(df_member, segment_col="member_casual", filters=filters)

    st.write("")
    st.subheader("Classic vs Electric over time")
    df_rideable = queries.daily_rideable_type(filters.systems, filters.month_start, filters.month_end)
    _render_stacked_panels(df_rideable, segment_col="rideable_type", filters=filters)


def _render_stacked_panels(df, *, segment_col: str, filters: Filters) -> None:
    """One stacked-bar timeseries per system, side by side."""
    if df.empty:
        empty_state()
        return
    cols, syss = system_columns(filters.systems)
    for col, system in zip(cols, syss):
        with col:
            system_header(system)
            sub = df[df["system"] == system]
            if sub.empty:
                empty_state(f"No data for {SYSTEM_LABEL[system]}.")
                continue
            fig = stacked_bar_timeseries(
                sub, x_col="started_date", y_col="total_rides", segment_col=segment_col
            )
            st.plotly_chart(fig, use_container_width=True)


main()
