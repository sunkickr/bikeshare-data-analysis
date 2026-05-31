"""Time Patterns page — implemented in Phase 4."""
from __future__ import annotations

import streamlit as st

from lib.filters import render_header_filters
from lib.theme import MUTED, apply_plotly_defaults

st.set_page_config(page_title="Time Patterns", page_icon="🚲", layout="wide")
apply_plotly_defaults()

st.title("Time Patterns")
render_header_filters()
st.divider()
st.markdown(
    f'<div style="padding:32px;text-align:center;color:{MUTED}">Coming next — peak-hour distribution and day-of-week patterns per system.</div>',
    unsafe_allow_html=True,
)
