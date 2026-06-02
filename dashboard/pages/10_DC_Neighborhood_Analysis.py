"""DC Neighborhood Analysis — click a neighbourhood on the map to see all
dimensions: ride volume, density, adoption rate, member mix, trip duration,
and Census population context.

Data: analytics_marts.agg_rides_by_neighborhood (dbt mart, month-grained)
Map boundaries: data/geo/dc_neighborhoods_osm.geojson (frozen OSM snapshot)
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib.db import run_query
from lib.filters import get_available_months
from lib.theme import BACKGROUND, MUTED, TEXT, apply_plotly_defaults

st.set_page_config(
    page_title="DC Neighborhood Analysis",
    page_icon="🏘️",
    layout="wide",
)
apply_plotly_defaults()

_REPO_ROOT = Path(__file__).parent.parent.parent

_BOUNDARY_OPTIONS = {
    "osm": {
        "label":       "OSM Neighborhoods (117)",
        "geo":         _REPO_ROOT / "data" / "geo" / "dc_neighborhoods_osm.geojson",
        "table":       "analytics_marts.agg_rides_by_neighborhood",
        "id_col":      "neighborhood_name",
        "display_col": "neighborhood_name",
        "feature_key": "properties.neighborhood_name",
    },
    "cluster": {
        "label":       "Planning Clusters (39)",
        "geo":         _REPO_ROOT / "data" / "geo" / "dc_clusters.geojson",
        "table":       "analytics_marts.agg_rides_by_cluster",
        "id_col":      "cluster_id",
        "display_col": "cluster_display_name",
        "feature_key": "properties.cluster_id",
    },
}

_METRICS = {
    "total_rides":            {"label": "Total rides",               "fmt": "{:,.0f}"},
    "rides_per_km2":          {"label": "Rides per km²",             "fmt": "{:,.0f}"},
    "rides_per_1k_residents": {"label": "Rides per 1,000 residents", "fmt": "{:,.0f}"},
    "member_pct":             {"label": "Member ride %",             "fmt": "{:.1f}"},
    "avg_duration_minutes":   {"label": "Avg trip duration (min)",   "fmt": "{:.1f}"},
}


@st.cache_data(ttl=3600, show_spinner=False)
def _load_data(table: str, id_col: str, month_start: date, month_end: date) -> pd.DataFrame:
    """Aggregate the month-grained mart over the selected date range."""
    return run_query(
        f"""
        SELECT
            {id_col}                                                           AS zone_id,
            SUM(total_rides)                                                   AS total_rides,
            SUM(member_rides)                                                  AS member_rides,
            SUM(casual_rides)                                                  AS casual_rides,
            ROUND(SUM(total_duration_seconds)
                  / NULLIF(SUM(total_rides), 0) / 60.0, 1)                   AS avg_duration_minutes,
            MAX(area_km2)                                                      AS area_km2,
            MAX(centroid_lat)                                                  AS centroid_lat,
            MAX(centroid_lng)                                                  AS centroid_lng,
            MAX(population)                                                    AS population,
            MAX(households)                                                    AS households,
            MAX(median_household_income)                                       AS median_household_income,
            ROUND(SUM(member_rides) * 100.0
                  / NULLIF(SUM(total_rides), 0), 1)                           AS member_pct,
            ROUND(SUM(total_rides) * 1000.0
                  / NULLIF(MAX(population), 0), 1)                            AS rides_per_1k_residents,
            ROUND(SUM(total_rides)
                  / NULLIF(MAX(area_km2), 0), 1)                              AS rides_per_km2
        FROM {table}
        WHERE started_month BETWEEN :start AND :end
        GROUP BY {id_col}
        ORDER BY total_rides DESC
        """,
        {"start": month_start, "end": month_end},
    )


@st.cache_data(show_spinner=False)
def _load_geojson(boundary_key: str) -> dict:
    return json.loads(_BOUNDARY_OPTIONS[boundary_key]["geo"].read_text())


def _fmt(value, fmt: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return fmt.format(value)


def _format_month(d: date) -> str:
    return d.strftime("%b %Y")


def _detail_card(row: pd.Series, display_name: str) -> None:
    st.markdown(f"### {display_name}")
    st.divider()

    def kv(label: str, value, fmt: str, help: str = "") -> None:
        st.metric(label=label, value=_fmt(value, fmt), help=help or None)

    st.markdown("**Ride volume**")
    c1, c2 = st.columns(2)
    with c1:
        kv("Total rides", row["total_rides"], "{:,.0f}")
    with c2:
        kv("Member %", row["member_pct"], "{:.1f}%",
           "Share of rides by registered members vs casual riders")

    st.markdown("**Normalised activity**")
    c1, c2 = st.columns(2)
    with c1:
        kv("Rides / km²", row["rides_per_km2"], "{:,.0f}",
           "Spatial density of use")
    with c2:
        kv("Rides / 1k residents", row["rides_per_1k_residents"], "{:,.0f}",
           "Residential adoption — very high for low-population areas")

    st.markdown("**Trip character**")
    c1, c2 = st.columns(2)
    with c1:
        kv("Avg duration (min)", row["avg_duration_minutes"], "{:.1f}")
    with c2:
        kv("Area (km²)", row["area_km2"], "{:.2f}")

    st.markdown("**Population context**")
    c1, c2 = st.columns(2)
    with c1:
        kv("Residents", row["population"], "{:,.0f}")
    with c2:
        kv("Median HH income", row["median_household_income"], "${:,.0f}")


def _polygon_outline(zone_id: str, geojson: dict, feature_key: str) -> tuple[list, list]:
    """Return (lats, lons) for the boundary ring of a GeoJSON polygon feature."""
    id_prop = feature_key.replace("properties.", "")
    for f in geojson["features"]:
        if f["properties"].get(id_prop) == zone_id:
            geom = f["geometry"]
            if geom["type"] == "Polygon":
                ring = geom["coordinates"][0]
            elif geom["type"] == "MultiPolygon":
                # Use the largest ring.
                ring = max(
                    (p[0] for p in geom["coordinates"]), key=len
                )
            else:
                return [], []
            return [c[1] for c in ring], [c[0] for c in ring]
    return [], []


def _display_name_for(zone_id: str, boundary: dict, geojson: dict) -> str:
    """Return the human-readable display name for a zone_id."""
    if boundary["display_col"] == boundary["id_col"]:
        return zone_id
    # Clusters: look up readable name from GeoJSON properties.
    id_prop = boundary["id_col"]
    for f in geojson["features"]:
        if f["properties"].get(id_prop) == zone_id:
            return f["properties"].get(boundary["display_col"], zone_id)
    return zone_id


def main() -> None:
    st.title("🏘️ DC Neighborhood Analysis")

    # ── Boundary type toggle ──────────────────────────────────────────────────
    boundary_key = st.radio(
        "Boundary definition",
        options=list(_BOUNDARY_OPTIONS.keys()),
        format_func=lambda k: _BOUNDARY_OPTIONS[k]["label"],
        horizontal=True,
        label_visibility="collapsed",
    )
    boundary = _BOUNDARY_OPTIONS[boundary_key]

    # ── Month filter ──────────────────────────────────────────────────────────
    months = get_available_months()
    if not months:
        st.error("No data available. Run `scripts/refresh_pipeline.sh` first.")
        st.stop()

    month_options = list(reversed(months))

    st.session_state.setdefault("nbhd_month_start", months[-1])
    st.session_state.setdefault("nbhd_month_end",   months[-1])
    st.session_state.setdefault("nbhd_is_range",    False)
    st.session_state.setdefault("nbhd_selected",    None)   # authoritative selection
    st.session_state.setdefault("nbhd_map_key",     0)      # incremented to reset Plotly state
    st.session_state.setdefault("nbhd_boundary",    None)

    # Clear selection when the boundary type changes.
    if st.session_state["nbhd_boundary"] != boundary_key:
        st.session_state["nbhd_selected"] = None
        st.session_state["nbhd_map_key"] += 1
        st.session_state["nbhd_boundary"] = boundary_key

    is_range = st.session_state["nbhd_is_range"]

    if is_range:
        cols = st.columns([2, 2, 1])
        start_col, end_col, toggle_col = cols
    else:
        cols = st.columns([3, 1])
        single_col, toggle_col = cols

    if is_range:
        with start_col:
            m_start = st.selectbox(
                "Start month", month_options,
                index=month_options.index(st.session_state["nbhd_month_start"]),
                format_func=_format_month, key="_nbhd_start",
            )
            st.session_state["nbhd_month_start"] = m_start
        with end_col:
            m_end = st.selectbox(
                "End month", month_options,
                index=month_options.index(st.session_state["nbhd_month_end"]),
                format_func=_format_month, key="_nbhd_end",
            )
            st.session_state["nbhd_month_end"] = m_end
        if m_start > m_end:
            m_start, m_end = m_end, m_start
    else:
        with single_col:
            chosen = st.selectbox(
                "Month", month_options,
                index=month_options.index(st.session_state["nbhd_month_start"]),
                format_func=_format_month, key="_nbhd_single",
            )
            st.session_state["nbhd_month_start"] = chosen
            st.session_state["nbhd_month_end"]   = chosen
            m_start = m_end = chosen

    with toggle_col:
        st.session_state["nbhd_is_range"] = st.toggle(
            "Multi-month", value=is_range
        )

    st.divider()

    df      = _load_data(boundary["table"], boundary["id_col"], m_start, m_end)
    geojson = _load_geojson(boundary_key)

    if df.empty:
        st.info("No neighbourhood data for the selected period.")
        st.stop()

    selected = st.session_state["nbhd_selected"]

    # Callback runs before the rerun, so `selected` is already None when the
    # sidebar renders on the next run — no second click needed.
    def _clear():
        st.session_state["nbhd_selected"] = None
        st.session_state["nbhd_map_key"] += 1

    # ── Sidebar: metric selector + detail card ───────────────────────────────
    # The ✕ button and hint text live inside detail_placeholder, which is
    # filled after all events are processed — so they always reflect the
    # current selection in a single run with no extra rerun.
    with st.sidebar:
        metric_key = st.selectbox(
            "Color map by",
            options=list(_METRICS.keys()),
            format_func=lambda k: _METRICS[k]["label"],
        )
        st.divider()
        detail_placeholder = st.empty()

    # ── Map ───────────────────────────────────────────────────────────────────
    p95 = df[metric_key].quantile(0.95)
    p05 = df[metric_key].quantile(0.05)

    fig = px.choropleth_mapbox(
        df,
        geojson=geojson,
        locations="zone_id",
        featureidkey=boundary["feature_key"],
        color=metric_key,
        color_continuous_scale="Blues",
        range_color=[p05, p95],
        hover_name="zone_id",
        hover_data={
            "total_rides":            True,
            "rides_per_km2":          True,
            "rides_per_1k_residents": True,
            "member_pct":             True,
            "zone_id":                False,
        },
        labels={
            "total_rides":            "Total rides",
            "rides_per_km2":          "Rides/km²",
            "rides_per_1k_residents": "Rides/1k residents",
            "member_pct":             "Member %",
        },
        mapbox_style="open-street-map",
        zoom=11.2,
        center={"lat": 38.907, "lon": -77.036},
        opacity=0.70,
        height=660,
    )

    # White polygon outline marks the selected zone — works for both map and
    # table-driven selections without adding a dot.
    if selected:
        lats, lons = _polygon_outline(selected, geojson, boundary["feature_key"])
        if lats:
            fig.add_trace(go.Scattermapbox(
                lat=lats, lon=lons,
                mode="lines",
                line=dict(width=3, color="#FFFFFF"),
                hoverinfo="skip",
                showlegend=False,
            ))

    fig.update_layout(
        paper_bgcolor=BACKGROUND,
        margin=dict(l=0, r=0, t=0, b=0),
        coloraxis_colorbar=dict(
            title=_METRICS[metric_key]["label"],
            thickness=14,
            len=0.5,
            bgcolor="rgba(14,17,23,0.85)",
            tickfont=dict(color=TEXT),
            titlefont=dict(color=TEXT),
        ),
    )

    event = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        key=f"nbhd_map_{boundary_key}_{st.session_state['nbhd_map_key']}",
    )

    # Map click — rerun so the outline and ✕ button are consistent.
    if event and event.selection and event.selection.points:
        clicked = event.selection.points[0].get("location")
        if clicked and clicked != st.session_state["nbhd_selected"]:
            st.session_state["nbhd_selected"] = clicked
            st.session_state["nbhd_map_key"] += 1
            st.rerun()

    # ── Full table with clickable rows ────────────────────────────────────────
    with st.expander("Full table — all neighbourhoods"):
        sort_col = st.selectbox(
            "Sort by",
            options=list(_METRICS.keys()),
            format_func=lambda k: _METRICS[k]["label"],
            key="table_sort",
        )
        sorted_df = df.sort_values(sort_col, ascending=False).reset_index(drop=True)
        display_df = sorted_df.rename(columns={
            "zone_id":                 "Zone",
            "total_rides":             "Total rides",
            "member_pct":              "Member %",
            "rides_per_km2":           "Rides/km²",
            "rides_per_1k_residents":  "Rides/1k residents",
            "avg_duration_minutes":    "Avg duration (min)",
            "population":              "Population",
            "median_household_income": "Median HH income",
        })[[
            "Zone", "Total rides", "Member %",
            "Rides/km²", "Rides/1k residents",
            "Avg duration (min)", "Population", "Median HH income",
        ]]

        table_event = st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"nbhd_table_{boundary_key}",
        )

        # Table row click — same rerun pattern as map click.
        if table_event.selection.rows:
            row_idx = table_event.selection.rows[0]
            zone_id = sorted_df.iloc[row_idx]["zone_id"]
            if zone_id != st.session_state["nbhd_selected"]:
                st.session_state["nbhd_selected"] = zone_id
                st.session_state["nbhd_map_key"] += 1
                st.rerun()

    # ── Fill detail placeholder once, after all events are processed ──────────
    # Placing the ✕ button here means it always reflects the current selection
    # in the same run — map clicks, table clicks, and the initial state all work.
    with detail_placeholder.container():
        if selected:
            hdr, clear_col = st.columns([5, 1])
            with hdr:
                st.caption("Selected")
            with clear_col:
                st.button("✕", key="clear_btn", help="Clear", on_click=_clear)
            match = df[df["zone_id"] == selected]
            if not match.empty:
                _detail_card(
                    match.iloc[0],
                    _display_name_for(selected, boundary, geojson),
                )
        else:
            st.caption("Click a neighbourhood on the map.")


main()
