"""Ride Activity page — implemented in Phase 2."""
from __future__ import annotations

import streamlit as st

from lib.filters import render_header_filters
from lib.theme import MUTED, apply_plotly_defaults

st.set_page_config(page_title="Ride Activity", page_icon="🚲", layout="wide")
apply_plotly_defaults()

st.title("Ride Activity")
render_header_filters()
st.divider()
st.markdown(
    f'<div style="padding:32px;text-align:center;color:{MUTED}">Coming next — daily volume, ride durations, member/casual + classic/electric splits over time.</div>',
    unsafe_allow_html=True,
)
