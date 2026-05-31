"""Header filter widgets, rendered at the top of every page.

Returns a Filters dataclass that pages consume. Filter state lives in st.session_state
so navigating between pages preserves selections.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from lib.db import run_query

SYSTEM_CHOICES = ["Both", "DC", "NYC"]
SYSTEM_TO_DB = {"DC": "capitalbikeshare", "NYC": "citibike"}


@dataclass(frozen=True)
class Filters:
    """User filter selections passed to every page.

    `month_start` and `month_end` are first-of-month dates. They're equal when the
    user picks a single month — the downstream query helpers already treat them
    as a closed range, so a single-month filter still goes through the same code
    path as a future multi-month filter.
    """
    systems: tuple[str, ...]   # the dbt `system` values to include
    month_start: date
    month_end: date

    @property
    def system_labels(self) -> list[str]:
        reverse = {v: k for k, v in SYSTEM_TO_DB.items()}
        return [reverse[s] for s in self.systems]

    @property
    def show_both(self) -> bool:
        return len(self.systems) > 1


@st.cache_data(ttl=3600, show_spinner=False)
def get_available_months() -> list[date]:
    """All distinct months (first-of-month dates) across both systems, ascending.

    agg_rides_daily has a `started_date` column at day grain — we truncate to month
    here rather than storing a separate `started_month` column. Cached for an hour
    because dbt rebuilds are weekly via cron.
    """
    df = run_query(
        "SELECT DISTINCT date_trunc('month', started_date)::date AS month "
        "FROM analytics_marts.agg_rides_daily "
        "ORDER BY month"
    )
    return [d.date() if isinstance(d, pd.Timestamp) else d for d in df["month"]]


def render_header_filters() -> Filters:
    """Render the header filter row above page content. Returns the chosen Filters.

    Single horizontal row. Off by default: one Month dropdown. Toggle "Multi-month"
    on and the single dropdown is replaced by two (Start / End) without changing
    the row height — labels on every widget keep the vertical alignment clean.
    State persists in st.session_state across page navigation.
    """
    months = get_available_months()
    if not months:
        st.error("No data available. Run `scripts/refresh_pipeline.sh` first.")
        st.stop()

    month_options = list(reversed(months))   # newest first in the dropdown
    default_month = months[-1]

    # Read the toggle's previous value before laying out columns — the column
    # count depends on it. The toggle widget itself renders inside the last
    # column and only takes effect on the next rerun.
    is_range = st.session_state.get("flt_is_range", False)

    if is_range:
        cols = st.columns([1.5, 2, 2, 1.5])
        system_col, start_col, end_col, toggle_col = cols
    else:
        cols = st.columns([1.5, 3, 1.5])
        system_col, single_col, toggle_col = cols

    with system_col:
        system_choice = st.selectbox(
            "System",
            SYSTEM_CHOICES,
            index=SYSTEM_CHOICES.index(st.session_state.get("flt_system", "Both")),
            key="flt_system",
        )

    if is_range:
        with start_col:
            prior_start = st.session_state.get("flt_range_start", default_month)
            m_start = st.selectbox(
                "Start month",
                month_options,
                index=month_options.index(prior_start) if prior_start in month_options else 0,
                format_func=_format_month,
                key="flt_range_start",
            )
        with end_col:
            prior_end = st.session_state.get("flt_range_end", default_month)
            m_end = st.selectbox(
                "End month",
                month_options,
                index=month_options.index(prior_end) if prior_end in month_options else 0,
                format_func=_format_month,
                key="flt_range_end",
            )
        if m_start > m_end:
            m_start, m_end = m_end, m_start
    else:
        with single_col:
            prior_month = st.session_state.get("flt_month", default_month)
            chosen = st.selectbox(
                "Month",
                month_options,
                index=month_options.index(prior_month) if prior_month in month_options else 0,
                format_func=_format_month,
                key="flt_month",
            )
            m_start = m_end = chosen

    with toggle_col:
        st.toggle(
            "Multi-month",
            value=is_range,
            key="flt_is_range",
            help="Switch to two dropdowns to aggregate across a month range.",
        )

    if system_choice == "Both":
        systems = ("capitalbikeshare", "citibike")
    else:
        systems = (SYSTEM_TO_DB[system_choice],)

    return Filters(systems=systems, month_start=m_start, month_end=m_end)


def _format_month(d: date) -> str:
    return d.strftime("%b %Y")
