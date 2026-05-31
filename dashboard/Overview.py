"""Bikeshare dashboard — Overview page (Streamlit entry point).

Streamlit treats the file passed to `streamlit run` as page #1; everything in
the `pages/` directory shows up below it in the sidebar nav, alphabetically by
filename (which is why the page files start with 1_, 2_, etc).
"""
from __future__ import annotations

import streamlit as st

from lib import queries
from lib.charts import (
    donut_chart,
    empty_state,
    format_hours,
    format_int,
    kpi_tile,
    system_columns,
    system_header,
)
from lib.filters import Filters, render_header_filters
from lib.theme import (
    DC_COLOR,
    NYC_COLOR,
    PASTEL_PALETTE,
    SYSTEM_COLOR,
    SYSTEM_LABEL,
    apply_plotly_defaults,
)

st.set_page_config(
    page_title="Bikeshare Dashboard",
    page_icon="🚲",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_plotly_defaults()


def main() -> None:
    st.title("Overview")
    filters = render_header_filters()
    st.divider()

    kpis = queries.overview_kpis(filters.systems, filters.month_start, filters.month_end)
    stations = queries.unique_station_count(filters.systems)
    members = queries.member_casual_breakdown(filters.systems, filters.month_start, filters.month_end)
    rideables = queries.rideable_type_breakdown(filters.systems, filters.month_start, filters.month_end)

    if kpis.empty:
        empty_state("No rides recorded in this month range for the selected system.")
        return

    _render_kpi_grid(kpis, stations, filters)
    st.write("")
    _render_donut_row("Member vs Casual", members, "member_casual", filters)
    st.write("")
    _render_donut_row("Classic vs Electric", rideables, "rideable_type", filters)


def _render_kpi_grid(kpis, stations, filters: Filters) -> None:
    """Five KPI rows: total rides, total hours, unique stations, member %, classic %.

    Each row has one column per selected system; the column header is the city label.
    """
    kpis_by_sys = {row["system"]: row for _, row in kpis.iterrows()}
    stations_by_sys = {row["system"]: row["unique_stations"] for _, row in stations.iterrows()}

    cols, syss = system_columns(filters.systems)
    for col, system in zip(cols, syss):
        with col:
            system_header(system)
            row = kpis_by_sys.get(system)
            if row is None:
                empty_state(f"No rides for {SYSTEM_LABEL[system]} in this window.")
                continue

            total_rides = row["total_rides"]
            total_hours = row["total_hours"]

            accent = SYSTEM_COLOR[system]
            tile_cols = st.columns(2)
            with tile_cols[0]:
                kpi_tile("Total Rides", format_int(total_rides), accent=accent)
            with tile_cols[1]:
                kpi_tile("Total Hours", format_hours(total_hours), accent=accent)


def _render_donut_row(title: str, df, segment_col: str, filters: Filters) -> None:
    """Render a row of donuts — one per system — for the given breakdown."""
    st.subheader(title)
    if df.empty:
        empty_state()
        return

    cols, syss = system_columns(filters.systems)
    for col, system in zip(cols, syss):
        with col:
            system_header(system)
            sub = df[df["system"] == system]
            if sub.empty:
                empty_state(f"No {title.lower()} data for {SYSTEM_LABEL[system]}.")
                continue
            # Two-color split: city identity color + first pastel for the "other" segment.
            colors = [SYSTEM_COLOR[system], PASTEL_PALETTE[0]] if len(sub) == 2 else PASTEL_PALETTE
            fig = donut_chart(
                sub,
                names_col=segment_col,
                values_col="total_rides",
                title=f"{SYSTEM_LABEL[system]} — {title}",
                color_sequence=colors,
            )
            st.plotly_chart(fig, use_container_width=True)


main()
