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

    Persistence model:
      - Single source of truth is `p_*` keys in st.session_state, which we own
        explicitly (set via direct writes). These survive page navigation in
        Streamlit's multipage app — only widget-bound state gets pruned.
      - Widgets render *without* a `key=` argument. Each render, we read the
        current value from `p_*` and pass it as `index=`/`value=` so the widget
        displays the right thing. We capture the widget's return and write back
        to `p_*` immediately. The widget never owns state we depend on.
    """
    months = get_available_months()
    if not months:
        st.error("No data available. Run `scripts/refresh_pipeline.sh` first.")
        st.stop()

    month_options = list(reversed(months))   # newest first in the dropdown
    default_month = months[-1]

    # Persistent state — survives page navigation because we set it explicitly.
    _init_persistent("p_system", "Both", SYSTEM_CHOICES)
    _init_persistent("p_month", default_month, month_options)
    _init_persistent("p_range_start", default_month, month_options)
    _init_persistent("p_range_end", default_month, month_options)
    _init_persistent("p_is_range", False, None)

    is_range = st.session_state["p_is_range"]

    if is_range:
        cols = st.columns([1.5, 2, 2, 1.5])
        system_col, start_col, end_col, toggle_col = cols
    else:
        cols = st.columns([1.5, 3, 1.5])
        system_col, single_col, toggle_col = cols

    with system_col:
        sys_idx = SYSTEM_CHOICES.index(st.session_state["p_system"])
        system_choice = st.selectbox("System", SYSTEM_CHOICES, index=sys_idx)
        st.session_state["p_system"] = system_choice

    if is_range:
        with start_col:
            idx = month_options.index(st.session_state["p_range_start"])
            m_start = st.selectbox(
                "Start month", month_options,
                index=idx, format_func=_format_month,
            )
            st.session_state["p_range_start"] = m_start
        with end_col:
            idx = month_options.index(st.session_state["p_range_end"])
            m_end = st.selectbox(
                "End month", month_options,
                index=idx, format_func=_format_month,
            )
            st.session_state["p_range_end"] = m_end
        if m_start > m_end:
            m_start, m_end = m_end, m_start
    else:
        with single_col:
            idx = month_options.index(st.session_state["p_month"])
            chosen = st.selectbox(
                "Month", month_options,
                index=idx, format_func=_format_month,
            )
            st.session_state["p_month"] = chosen
            m_start = m_end = chosen

    with toggle_col:
        new_is_range = st.toggle(
            "Multi-month",
            value=is_range,
            help="Switch to two dropdowns to aggregate across a month range.",
        )
        st.session_state["p_is_range"] = new_is_range

    if system_choice == "Both":
        systems = ("capitalbikeshare", "citibike")
    else:
        systems = (SYSTEM_TO_DB[system_choice],)

    # DEBUG — remove once filter persistence is verified
    with st.expander("🔧 Debug: session state (for filter persistence diagnosis)"):
        st.json({
            "p_system": str(st.session_state.get("p_system")),
            "p_month": str(st.session_state.get("p_month")),
            "p_range_start": str(st.session_state.get("p_range_start")),
            "p_range_end": str(st.session_state.get("p_range_end")),
            "p_is_range": st.session_state.get("p_is_range"),
            "resolved_systems": list(systems),
            "resolved_m_start": str(m_start),
            "resolved_m_end": str(m_end),
        })

    return Filters(systems=systems, month_start=m_start, month_end=m_end)


def _init_persistent(key: str, default, valid_options) -> None:
    """Init a persistent (user-owned) session state key. Resets if the saved
    value is stale (no longer in valid_options) — safe even when filter options
    change between dbt runs.
    """
    if key not in st.session_state:
        st.session_state[key] = default
    elif valid_options is not None and st.session_state[key] not in valid_options:
        st.session_state[key] = default


def _format_month(d: date) -> str:
    return d.strftime("%b %Y")
