"""Stations & Routes page — implemented in Phase 3."""
from __future__ import annotations

import streamlit as st

from lib.filters import render_header_filters
from lib.theme import MUTED, apply_plotly_defaults

st.set_page_config(page_title="Stations & Routes", page_icon="🚲", layout="wide")
apply_plotly_defaults()

st.title("Stations & Routes")
render_header_filters()
st.divider()
st.markdown(
    f'<div style="padding:32px;text-align:center;color:{MUTED}">Coming next — top 10 start/end stations and top 5 popular routes per system.</div>',
    unsafe_allow_html=True,
)
