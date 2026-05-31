"""Time Patterns — hour-of-day and day-of-week distributions, with the
busiest/quietest day callout repeated from Ride Activity for context.

Two bar charts per section (side by side, one per system). When the user
filters to a single system, each section collapses to a single panel.
"""
from __future__ import annotations

import streamlit as st

from lib import queries
from lib.charts import (
    empty_state,
    format_int,
    kpi_tile,
    simple_bar_chart,
    system_columns,
    system_header,
)
from lib.filters import Filters, render_header_filters
from lib.theme import SYSTEM_COLOR, SYSTEM_LABEL, apply_plotly_defaults

st.set_page_config(page_title="Time Patterns", page_icon="🚲", layout="wide")
apply_plotly_defaults()


def main() -> None:
    st.title("Time Patterns")
    filters = render_header_filters()
    st.divider()

    _section_hour(filters)
    st.divider()
    _section_dow(filters)
    st.divider()
    _section_busiest_quietest(filters)


def _section_hour(filters: Filters) -> None:
    """24-bar distribution: rides per hour-of-day (0-23) per system."""
    st.subheader("Rides by hour of day")
    df = queries.rides_by_hour(filters.systems, filters.month_start, filters.month_end)
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
            fig = simple_bar_chart(
                sub,
                x_col="started_hour",
                y_col="rides",
                color=SYSTEM_COLOR[system],
                hover_x_label="Hour",
                height=320,
            )
            st.plotly_chart(fig, use_container_width=True)


def _section_dow(filters: Filters) -> None:
    """7-bar distribution: rides per day of week, preserving the model's day order."""
    st.subheader("Rides by day of week")
    df = queries.rides_by_dow(filters.systems, filters.month_start, filters.month_end)
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
            fig = simple_bar_chart(
                sub,
                x_col="started_dow_name",
                y_col="rides",
                color=SYSTEM_COLOR[system],
                preserve_x_order=True,
                hover_x_label="Day",
                height=320,
            )
            st.plotly_chart(fig, use_container_width=True)


def _section_busiest_quietest(filters: Filters) -> None:
    """Echoes the busiest/quietest callout from Ride Activity. Shares the same
    underlying query, so the cache is reused across both pages.
    """
    st.subheader("Busiest and quietest days")
    df = queries.busiest_and_quietest_day(filters.systems, filters.month_start, filters.month_end)
    if df.empty:
        empty_state()
        return

    by_sys = {(row["system"], row["kind"]): row for _, row in df.iterrows()}

    cols, syss = system_columns(filters.systems)
    for col, system in zip(cols, syss):
        with col:
            system_header(system)
            accent = SYSTEM_COLOR[system]
            busiest = by_sys.get((system, "busiest"))
            quietest = by_sys.get((system, "quietest"))
            tile_cols = st.columns(2)
            with tile_cols[0]:
                if busiest is not None:
                    kpi_tile(
                        "Busiest Day",
                        busiest["started_date"].strftime("%b %d"),
                        accent=accent,
                        caption=f"{format_int(busiest['rides'])} rides",
                    )
                else:
                    kpi_tile("Busiest Day", "—", accent=accent)
            with tile_cols[1]:
                if quietest is not None:
                    kpi_tile(
                        "Quietest Day",
                        quietest["started_date"].strftime("%b %d"),
                        accent=accent,
                        caption=f"{format_int(quietest['rides'])} rides",
                    )
                else:
                    kpi_tile("Quietest Day", "—", accent=accent)


main()
