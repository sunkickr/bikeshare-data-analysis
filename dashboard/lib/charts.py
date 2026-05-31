"""Small chart wrappers + KPI tile renderer. Imports `theme` for colors so every
chart on every page comes out consistent without each page reaching for hex codes.
"""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.theme import MUTED, PASTEL_PALETTE, SYSTEM_COLOR, SYSTEM_LABEL, TEXT


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
