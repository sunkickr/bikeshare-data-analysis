"""Small chart wrappers + KPI tile renderer. Imports `theme` for colors so every
chart on every page comes out consistent without each page reaching for hex codes.
"""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.theme import (
    BACKGROUND,
    DC_COLOR,
    MAP_BASE_COLOR,
    MAP_CENTER,
    MAP_END_COLOR,
    MAP_ROUTE_COLOR,
    MAP_START_COLOR,
    MAP_ZOOM,
    MUTED,
    NYC_COLOR,
    PASTEL_PALETTE,
    SEGMENT_COLORS,
    SURFACE,
    SYSTEM_COLOR,
    SYSTEM_LABEL,
    TEXT,
)


def kpi_tile(label: str, value: str, *, accent: str | None = None, caption: str | None = None) -> None:
    """Render a single KPI tile with a large value and small label.

    Streamlit's built-in st.metric is fine but doesn't accept color overrides;
    this version puts the colored accent strip on top so DC tiles look DC-y.
    """
    bar = f'<div style="background:{accent or PASTEL_PALETTE[0]};height:3px;border-radius:2px;margin-bottom:8px"></div>' if accent else ""
    cap_html = f'<div style="color:{MUTED};font-size:0.8rem;margin-top:4px">{caption}</div>' if caption else ""
    st.markdown(
        f"""
        <div style="padding:14px 16px;background:#1A1D24;border-radius:8px">
          {bar}
          <div style="color:{MUTED};font-size:0.85rem;text-transform:uppercase;letter-spacing:0.05em">{label}</div>
          <div style="color:{TEXT};font-size:1.8rem;font-weight:600;line-height:1.2;margin-top:2px">{value}</div>
          {cap_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def donut_chart(
    df: pd.DataFrame,
    *,
    names_col: str,
    values_col: str,
    title: str,
    color_sequence: Iterable[str] | None = None,
) -> go.Figure:
    """A donut chart with the inherited dark Plotly template applied.

    Labels render *outside* the donut on the dark background — light pastel slices
    can't host light text without contrast loss.
    """
    fig = go.Figure(
        data=[
            go.Pie(
                labels=df[names_col],
                values=df[values_col],
                hole=0.55,
                marker=dict(colors=list(color_sequence) if color_sequence else PASTEL_PALETTE),
                textinfo="label+percent",
                textposition="outside",
                textfont=dict(color=TEXT, size=13),
                outsidetextfont=dict(color=TEXT, size=13),
                automargin=True,
                sort=False,
            )
        ]
    )
    fig.update_layout(
        title=dict(text=title, font=dict(size=15)),
        showlegend=False,
        height=360,
        margin=dict(l=20, r=20, t=50, b=30),
    )
    return fig


def multi_system_line_chart(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    system_col: str = "system",
    y_title: str = "",
    height: int = 380,
) -> go.Figure:
    """One line per system, colored with the city's identity color.

    Used when the comparison axis is *time* and both systems share the same x-axis
    — overlaying them on one chart is more informative than side-by-side panels.
    """
    fig = go.Figure()
    for system in df[system_col].unique():
        sub = df[df[system_col] == system].sort_values(x_col)
        label = SYSTEM_LABEL.get(system, system)
        fig.add_trace(
            go.Scatter(
                x=sub[x_col],
                y=sub[y_col],
                mode="lines",
                name=label,
                line=dict(color=SYSTEM_COLOR.get(system, PASTEL_PALETTE[0]), width=2.5),
                hovertemplate=f"<b>{label}</b><br>%{{x|%b %d, %Y}}<br>%{{y:,.0f}} rides<extra></extra>",
            )
        )
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=height,
        xaxis_title=None,
        yaxis_title=y_title,
        hovermode="x unified",
    )
    return fig


def stacked_bar_timeseries(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    segment_col: str,
    color_map: dict[str, str] | None = None,
    height: int = 320,
    y_title: str = "Rides",
) -> go.Figure:
    """Daily stacked bars. Segments share the page's pastel palette by default;
    pass `color_map={segment_value: hex}` for stable identity coloring (member /
    casual, classic / electric) — falls back to SEGMENT_COLORS, then to PASTEL.
    """
    fig = go.Figure()
    segments = sorted(df[segment_col].unique())
    for i, segment in enumerate(segments):
        sub = df[df[segment_col] == segment].sort_values(x_col)
        color = (
            (color_map or {}).get(segment)
            or SEGMENT_COLORS.get(segment)
            or PASTEL_PALETTE[i % len(PASTEL_PALETTE)]
        )
        fig.add_trace(
            go.Bar(
                x=sub[x_col],
                y=sub[y_col],
                name=str(segment).replace("_", " ").title(),
                marker_color=color,
                hovertemplate="%{x|%b %d}<br>%{y:,.0f}<extra></extra>",
            )
        )
    fig.update_layout(
        barmode="stack",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=height,
        xaxis_title=None,
        yaxis_title=y_title,
    )
    return fig


def horizontal_bar_chart(
    df: pd.DataFrame,
    *,
    label_col: str,
    value_col: str,
    color: str,
    height: int = 360,
    value_format: str = "compact",
) -> go.Figure:
    """Horizontal bar chart for top-N rankings. Sorts ascending so the *highest*
    value lands at the *top* (Plotly draws bars bottom-to-top).

    `value_format` controls the trailing text on each bar:
        - "compact" → 25K / 1.5M
        - "int"     → 25,123
    """
    sub = df.sort_values(value_col, ascending=True)
    formatter = format_compact if value_format == "compact" else (lambda v: f"{int(v):,}")
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=sub[value_col],
            y=sub[label_col],
            orientation="h",
            marker_color=color,
            text=[formatter(v) for v in sub[value_col]],
            textposition="outside",
            textfont=dict(color=TEXT, size=11),
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} rides<extra></extra>",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        height=height,
        showlegend=False,
        xaxis_title=None,
        yaxis_title=None,
        margin=dict(l=10, r=70, t=10, b=30),
    )
    fig.update_yaxes(automargin=True, tickfont=dict(size=11))
    fig.update_xaxes(showticklabels=False)
    return fig


def station_route_map(
    all_stations_df: pd.DataFrame,
    start_df: pd.DataFrame,
    end_df: pd.DataFrame,
    routes_df: pd.DataFrame,
    *,
    system: str,
    height: int = 460,
) -> go.Figure:
    """Plotly mapbox map for one system. Four z-ordered layers:

      1. (bottom) Dim slate dots for every station in the network — context.
      2. Muted gray lines for top routes, width proportional to ride count.
      3. Light-orange markers for top end stations.
      4. (top) Mint markers for top start stations.

    Coordinate-missing rows are dropped per-trace so an incomplete LEFT JOIN
    against dim_stations doesn't break the figure.
    """
    fig = go.Figure()

    # 1. All stations background layer — small dim dots, hidden from legend.
    base = all_stations_df.dropna(subset=["lat", "lng"])
    if not base.empty:
        fig.add_trace(
            go.Scattermapbox(
                lat=base["lat"],
                lon=base["lng"],
                mode="markers",
                marker=go.scattermapbox.Marker(
                    size=5,
                    color=MAP_BASE_COLOR,
                    opacity=0.45,
                ),
                text=base["station_name"],
                hovertemplate="<b>%{text}</b><extra></extra>",
                name="All stations",
                showlegend=False,
            )
        )

    # 2. Route lines — one Scattermapbox trace per route so width can be per-route
    # (Plotly Scattermapbox supports per-trace line width but not per-segment).
    routes = routes_df.dropna(subset=["start_lat", "start_lng", "end_lat", "end_lng"])
    if not routes.empty:
        widths = _scale(routes["rides"], 3.0, 9.0)
        for (_, row), width in zip(routes.iterrows(), widths):
            fig.add_trace(
                go.Scattermapbox(
                    lat=[row["start_lat"], row["end_lat"]],
                    lon=[row["start_lng"], row["end_lng"]],
                    mode="lines",
                    line=dict(color=MAP_ROUTE_COLOR, width=float(width)),
                    opacity=0.85,
                    hovertemplate=(
                        f"<b>{row['route_label']}</b><br>"
                        f"{int(row['rides']):,} rides<extra></extra>"
                    ),
                    name="Top routes",
                    showlegend=False,
                    legendgroup="routes",
                )
            )
        # Single visible legend entry for the route group.
        fig.add_trace(
            go.Scattermapbox(
                lat=[None], lon=[None], mode="lines",
                line=dict(color=MAP_ROUTE_COLOR, width=4),
                name="Top routes", legendgroup="routes", showlegend=True,
            )
        )

    # 3. End station markers — drawn LARGER than start markers so they form an
    # orange "halo" around the mint center when a station is in both top-10 lists
    # (very common for hub stations).
    ends = end_df.dropna(subset=["lat", "lng"])
    if not ends.empty:
        sizes = _scale(ends["rides"], 16, 36)
        fig.add_trace(
            go.Scattermapbox(
                lat=ends["lat"],
                lon=ends["lng"],
                mode="markers",
                marker=go.scattermapbox.Marker(
                    size=sizes.tolist(),
                    color=MAP_END_COLOR,
                    opacity=0.95,
                ),
                text=ends["station_name"],
                customdata=ends["rides"],
                hovertemplate="<b>%{text}</b><br>%{customdata:,} ends<extra></extra>",
                name="Top end stations",
            )
        )

    # 4. Start station markers — smaller than end markers so the orange halo
    # behind shows for "both" stations; drawn on top so mint reads as primary.
    starts = start_df.dropna(subset=["lat", "lng"])
    if not starts.empty:
        sizes = _scale(starts["rides"], 10, 26)
        fig.add_trace(
            go.Scattermapbox(
                lat=starts["lat"],
                lon=starts["lng"],
                mode="markers",
                marker=go.scattermapbox.Marker(
                    size=sizes.tolist(),
                    color=MAP_START_COLOR,
                    opacity=0.95,
                ),
                text=starts["station_name"],
                customdata=starts["rides"],
                hovertemplate="<b>%{text}</b><br>%{customdata:,} starts<extra></extra>",
                name="Top start stations",
            )
        )

    center_lat, center_lng = MAP_CENTER.get(system, (0.0, 0.0))
    fig.update_layout(
        mapbox=dict(
            style="carto-darkmatter",
            center=dict(lat=center_lat, lon=center_lng),
            zoom=MAP_ZOOM,
        ),
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=0.02,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(14, 17, 23, 0.7)",
            bordercolor=SURFACE,
            borderwidth=1,
        ),
    )
    return fig


def ranking_highlight_map(
    geojson: dict,
    *,
    feature_key: str,
    zone_id: str,
    accent: str,
    center_lat: float,
    center_lng: float,
    zoom: float = 12.0,
    height: int = 360,
) -> go.Figure:
    """A DC choropleth that highlights a single neighborhood — the winner of a
    ranking section — in `accent`, with every other zone left dim.

    Built for the Neighborhood Rankings page: static (no click handling), centered
    on the winner's centroid (which the mart carries, so no centroid math here).
    `open-street-map` light basemap matches page 10 so the colored polygon pops.

    Other neighborhoods are left clear (no fill) — only their boundary lines show,
    drawn as a Mapbox `line` layer — so the basemap reads through and the winner is
    the only filled zone. `feature_key` is the GeoJSON property path
    (e.g. "properties.neighborhood_name"); `zone_id` is the winner's value for it.
    """
    # Winner-only fill, with hover. featureidkey matches this single location to
    # its polygon in the geojson.
    fig = go.Figure(
        go.Choroplethmapbox(
            geojson=geojson,
            locations=[zone_id],
            featureidkey=feature_key,
            z=[1],
            colorscale=[[0.0, accent], [1.0, accent]],
            showscale=False,
            marker=dict(line=dict(color=BACKGROUND, width=1), opacity=0.82),
            hovertext=[zone_id],
            hoverinfo="text",
        )
    )
    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=center_lat, lon=center_lng),
            zoom=zoom,
            # Every neighborhood boundary as a clear outline (no fill) beneath the
            # winner's filled polygon — "the lines are there" for context.
            layers=[dict(
                sourcetype="geojson",
                source=geojson,
                type="line",
                color=MAP_BASE_COLOR,
                line=dict(width=1),
            )],
        ),
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=BACKGROUND,
    )
    return fig


def _scale(series: pd.Series, lo: float, hi: float) -> pd.Series:
    """Linearly scale a numeric series into the [lo, hi] range. Safe when min == max."""
    values = series.astype(float)
    vmin, vmax = values.min(), values.max()
    if vmin == vmax:
        # All values equal — return the midpoint so markers/lines render at a
        # consistent visible size rather than collapsing to zero.
        mid = (lo + hi) / 2.0
        return pd.Series([mid] * len(values), index=values.index)
    return lo + (values - vmin) * (hi - lo) / (vmax - vmin)


def simple_bar_chart(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    color: str,
    y_title: str = "Rides",
    height: int = 320,
    preserve_x_order: bool = False,
    hover_x_label: str = "",
) -> go.Figure:
    """Single-color vertical bar chart for distributions (hour-of-day, day-of-week).

    `preserve_x_order=True` pins the x-axis category order to the DataFrame's
    order — important when the x values are non-numeric (e.g. weekday names)
    and Plotly would otherwise alphabetize them.
    """
    fig = go.Figure()
    label = hover_x_label or x_col
    fig.add_trace(
        go.Bar(
            x=df[x_col],
            y=df[y_col],
            marker_color=color,
            hovertemplate=f"<b>{label}: %{{x}}</b><br>%{{y:,.0f}} rides<extra></extra>",
        )
    )
    fig.update_layout(
        showlegend=False,
        height=height,
        xaxis_title=None,
        yaxis_title=y_title,
    )
    if preserve_x_order:
        fig.update_xaxes(categoryorder="array", categoryarray=df[x_col].tolist())
    return fig


def comparison_tile(
    label: str,
    dc_value: float | int | None,
    nyc_value: float | int | None,
    format_fn=None,
) -> None:
    """A two-bar tile comparing DC vs NYC for a single metric. Used on the
    City Comparison page. Bar widths are scaled to the larger of the two values
    so you can see who leads at a glance.
    """
    formatter = format_fn or format_int

    def _val(v):
        return 0.0 if v is None else float(v)

    dc_v, nyc_v = _val(dc_value), _val(nyc_value)
    max_val = max(dc_v, nyc_v, 1.0)
    dc_pct = (dc_v / max_val) * 100
    nyc_pct = (nyc_v / max_val) * 100

    dc_text = "—" if dc_value is None else formatter(dc_value)
    nyc_text = "—" if nyc_value is None else formatter(nyc_value)

    st.markdown(
        f"""
        <div style="padding:16px;background:{SURFACE};border-radius:8px;margin-bottom:12px">
            <div style="color:{MUTED};font-size:0.8rem;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:12px">{label}</div>
            <div style="display:flex;justify-content:space-between;color:{DC_COLOR};font-size:0.9rem;margin-bottom:3px">
                <span style="font-weight:600">DC</span><span>{dc_text}</span>
            </div>
            <div style="background:#0E1117;height:6px;border-radius:3px;margin-bottom:10px;overflow:hidden">
                <div style="background:{DC_COLOR};width:{dc_pct:.1f}%;height:100%"></div>
            </div>
            <div style="display:flex;justify-content:space-between;color:{NYC_COLOR};font-size:0.9rem;margin-bottom:3px">
                <span style="font-weight:600">NYC</span><span>{nyc_text}</span>
            </div>
            <div style="background:#0E1117;height:6px;border-radius:3px;overflow:hidden">
                <div style="background:{NYC_COLOR};width:{nyc_pct:.1f}%;height:100%"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_pct(p: float | None, *, decimals: int = 1) -> str:
    """Format a 0-1 share as a percent string. `format_pct(0.527)` → '52.7%'."""
    if p is None:
        return "—"
    return f"{p * 100:.{decimals}f}%"


def format_minutes(m: float | None) -> str:
    """Compact minutes formatter — '12.5 min' for sub-100, '1.2k min' for longer."""
    if m is None:
        return "—"
    if m >= 1000:
        return f"{m / 1000:.1f}k min"
    if m >= 100:
        return f"{m:.0f} min"
    return f"{m:.1f} min"


def empty_state(message: str = "No data for this selection.") -> None:
    """Render a muted placeholder when a filter combination has zero rows."""
    st.markdown(
        f'<div style="padding:24px;text-align:center;color:{MUTED};background:#1A1D24;border-radius:8px">{message}</div>',
        unsafe_allow_html=True,
    )


def system_columns(systems: tuple[str, ...]) -> tuple[list, list[str]]:
    """Return (streamlit_columns, system_keys) sized to the number of systems.

    When the user picks one system, returns a single full-width column.
    """
    cols = st.columns(len(systems)) if len(systems) > 1 else [st.container()]
    return cols, list(systems)


def system_header(system: str) -> None:
    """Render the colored 'DC' / 'NYC' header at the top of a per-system column."""
    label = SYSTEM_LABEL[system]
    color = SYSTEM_COLOR[system]
    st.markdown(
        f'<div style="border-left:3px solid {color};padding-left:10px;margin-bottom:8px">'
        f'<span style="color:{color};font-weight:600;font-size:1.1rem">{label}</span></div>',
        unsafe_allow_html=True,
    )


def format_int(n: float | int) -> str:
    """Comma-separated integer. Use for small counts where exact digits matter."""
    return f"{int(n):,}"


def format_compact(n: float | int) -> str:
    """Compact number formatting: 25,000,000 → '25.0M'. Used for KPI tiles where
    space is scarce. Mirrors how dashboards like Stripe and Mixpanel display
    headline metrics — readable at a glance, exact value still in the tooltip.
    """
    n = float(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000_000:
        return f"{sign}{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{sign}{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{sign}{n / 1_000:.0f}K"
    if n >= 1_000:
        return f"{sign}{n / 1_000:.1f}K"
    return f"{sign}{int(n)}"


def format_hours(h: float) -> str:
    """Compact hours formatting — same pattern as format_compact."""
    if h >= 1_000_000:
        return f"{h / 1_000_000:.1f}M hrs"
    if h >= 10_000:
        return f"{h / 1_000:.0f}K hrs"
    if h >= 1_000:
        return f"{h / 1_000:.1f}K hrs"
    return f"{h:,.0f} hrs"
