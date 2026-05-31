"""Small chart wrappers + KPI tile renderer. Imports `theme` for colors so every
chart on every page comes out consistent without each page reaching for hex codes.
"""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.theme import (
    DC_COLOR,
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
