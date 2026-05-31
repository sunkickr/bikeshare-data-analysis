"""City Comparison page — implemented in Phase 4."""
from __future__ import annotations

import streamlit as st

from lib.filters import render_header_filters
from lib.theme import MUTED, apply_plotly_defaults

st.set_page_config(page_title="City Comparison", page_icon="🚲", layout="wide")
apply_plotly_defaults()

st.title("City Comparison")
render_header_filters()
st.divider()
st.markdown(
    f'<div style="padding:32px;text-align:center;color:{MUTED}">Coming next — paired horizontal bars comparing DC vs NYC across every headline metric.</div>',
    unsafe_allow_html=True,
)
