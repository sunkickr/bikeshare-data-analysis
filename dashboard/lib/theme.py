"""Colors, Plotly templates, and per-system identity colors."""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

DC_COLOR = "#A5B4FC"      # periwinkle
NYC_COLOR = "#FCA5A5"     # salmon

PASTEL_PALETTE = [
    "#86EFAC",            # mint
    "#FDE68A",            # butter
    "#C4B5FD",            # lavender
    "#F9A8D4",            # rose
    "#A5B4FC",            # periwinkle (DC)
    "#FCA5A5",            # salmon (NYC)
]

BACKGROUND = "#0E1117"
SURFACE = "#1A1D24"
TEXT = "#E6E6E6"
MUTED = "#9CA3AF"

SYSTEM_COLOR = {
    "capitalbikeshare": DC_COLOR,
    "citibike": NYC_COLOR,
}

SYSTEM_LABEL = {
    "capitalbikeshare": "DC",
    "citibike": "NYC",
}

# Stable segment colors so member/casual and classic/electric look the same
# across the Overview, Ride Activity, and (future) City Comparison pages.
SEGMENT_COLORS = {
    "member": "#86EFAC",         # mint
    "casual": "#FDE68A",         # butter
    "classic_bike": "#C4B5FD",   # lavender
    "electric_bike": "#F9A8D4",  # rose
}

# Stations & Routes map palette. Distinct from system identity colors so the
# top-N highlights don't compete with the DC/NYC column headers.
MAP_BASE_COLOR = "#4B5563"    # slate — dim background "all stations" layer
MAP_START_COLOR = "#86EFAC"   # mint — top start stations
MAP_END_COLOR = "#FDBA74"     # light orange — top end stations
MAP_ROUTE_COLOR = "#E5E7EB"   # light neutral — route lines (high contrast on dark basemap)

# Initial map center + zoom per system. Centroid of each system's bounding box,
# chosen so the top-10 markers comfortably fit at zoom level 11.
MAP_CENTER = {
    "capitalbikeshare": (38.92, -77.03),  # roughly U Street, Washington DC
    "citibike":         (40.73, -73.99),  # roughly NoHo, Manhattan
}
MAP_ZOOM = 11


def apply_plotly_defaults() -> None:
    """Register a dark Plotly template tuned to match the Streamlit dark theme."""
    template = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=BACKGROUND,
            plot_bgcolor=BACKGROUND,
            font=dict(color=TEXT, family="-apple-system, system-ui, sans-serif"),
            colorway=PASTEL_PALETTE,
            xaxis=dict(gridcolor=SURFACE, zerolinecolor=SURFACE),
            yaxis=dict(gridcolor=SURFACE, zerolinecolor=SURFACE),
            margin=dict(l=40, r=20, t=40, b=40),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
        )
    )
    pio.templates["bikeshare_dark"] = template
    pio.templates.default = "bikeshare_dark"
