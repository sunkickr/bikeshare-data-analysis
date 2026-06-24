"""Live Station Map — real-time Capital Bikeshare availability across DC.

Auto-refreshes on an interval. Reads analytics_marts.agg_cabi_station_availability,
which is fed by the streaming pipeline (GBFS → Kafka → Postgres → dbt).

DC-only and intentionally isolated from the global System filter (same posture as
the DC Neighborhood page) — it never calls render_header_filters().
"""
from __future__ import annotations

import streamlit as st

from lib import queries
from lib.charts import empty_state, format_int, kpi_tile, live_availability_map
from lib.theme import DC_COLOR, MUTED, apply_plotly_defaults

st.set_page_config(page_title="Live Station Map", page_icon="📍", layout="wide")
apply_plotly_defaults()

REFRESH_SECONDS = 60


@st.fragment(run_every=REFRESH_SECONDS)
def render_live_map() -> None:
    """Only this fragment re-runs on the interval — the rest of the page is static.
    The query's short cache TTL (30s) ensures each refresh pulls fresh data."""
    df = queries.live_station_availability()
    if df.empty:
        empty_state("No live availability yet — is the streaming consumer running, "
                    "and has agg_cabi_station_availability been built?")
        return

    # Merge in the per-station change since the previous snapshot (powers the
    # map halo + the "Stations changed" KPI).
    changes = queries.live_station_changes()
    df = df.merge(changes, on="station_id", how="left")

    bikes = int(df["num_bikes_available"].sum())
    ebikes = int(df["num_ebikes_available"].sum())
    docks = int(df["num_docks_available"].sum())
    empty_stations = int((df["num_bikes_available"] == 0).sum())
    full_stations = int((df["num_docks_available"] == 0).sum())
    changed_stations = int((df["bikes_delta"].fillna(0) != 0).sum())
    as_of = df["as_of"].max()

    cols = st.columns(6)
    with cols[0]:
        kpi_tile("Bikes available", format_int(bikes), accent=DC_COLOR)
    with cols[1]:
        kpi_tile("E-bikes", format_int(ebikes), accent=DC_COLOR)
    with cols[2]:
        kpi_tile("Docks free", format_int(docks), accent=DC_COLOR)
    with cols[3]:
        kpi_tile("Empty stations", format_int(empty_stations), accent=DC_COLOR, caption="0 bikes")
    with cols[4]:
        kpi_tile("Full stations", format_int(full_stations), accent=DC_COLOR, caption="0 docks")
    with cols[5]:
        kpi_tile("Stations changed", format_int(changed_stations), accent="#F8FAFC", caption="since last update")

    st.write("")
    st.plotly_chart(live_availability_map(df), use_container_width=True)
    st.caption(
        f"{len(df):,} stations · data as of {as_of:%b %d, %Y %H:%M} · "
        f"auto-refreshes every {REFRESH_SECONDS}s"
    )


def main() -> None:
    st.title("Live Station Map")
    st.markdown(
        f"<span style='color:{MUTED}'>Real-time Capital Bikeshare availability across DC, "
        f"streamed GBFS → Kafka → Postgres → dbt. Each dot is a station, colored "
        f"red (empty) → green (full) and sized by dock capacity.</span>",
        unsafe_allow_html=True,
    )
    st.divider()
    render_live_map()


main()
