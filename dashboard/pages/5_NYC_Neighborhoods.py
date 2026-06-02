"""Temporary exploration page — NYC Neighborhood Tabulation Areas (NTAs).

262 NTA polygons from NYC Open Data, color-coded by borough. Use this to
understand which neighborhoods exist in the dataset and where their boundaries
fall before deciding on a ranking methodology.

Not connected to the database — fetches GeoJSON from NYC Open Data at startup
and caches it for 24 hours.
"""
from __future__ import annotations

import json
import urllib.request
from urllib.error import URLError

import pandas as pd
import plotly.express as px
import streamlit as st

from lib.theme import BACKGROUND, PASTEL_PALETTE, TEXT, MUTED, apply_plotly_defaults

st.set_page_config(page_title="NYC Neighborhoods (Explore)", page_icon="🗺️", layout="wide")
apply_plotly_defaults()

_NTA_URL = "https://data.cityofnewyork.us/resource/9nt8-h7nd.geojson?$limit=300"

# One color per borough, drawn from the dashboard's existing pastel palette.
_BOROUGH_COLORS = {
    "Manhattan": "#F9A8D4",    # rose
    "Brooklyn":  "#86EFAC",    # mint
    "Queens":    "#FDE68A",    # butter
    "Bronx":     "#C4B5FD",    # lavender
    "Staten Island": "#A5B4FC", # periwinkle
}


@st.cache_data(show_spinner="Loading NYC neighborhood boundaries…", ttl=86_400)
def _load() -> tuple[dict, pd.DataFrame]:
    req = urllib.request.Request(_NTA_URL, headers={"User-Agent": "bikeshare-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        geojson = json.load(resp)

    rows = [
        {
            "nta2020":  f["properties"].get("nta2020", ""),
            "ntaname":  f["properties"].get("ntaname", ""),
            "boroname": f["properties"].get("boroname", ""),
            "ntatype":  f["properties"].get("ntatype", ""),
        }
        for f in geojson["features"]
    ]
    return geojson, pd.DataFrame(rows)


def main() -> None:
    st.title("🗺️ NYC Neighborhood Boundaries")
    st.caption(
        "Temporary exploration · 262 Neighborhood Tabulation Areas from NYC Open Data · "
        "Color = borough · Hover for neighborhood name"
    )

    try:
        geojson, df = _load()
    except URLError as e:
        st.error(f"Could not fetch NYC neighborhood data: {e}")
        st.stop()

    # ── Sidebar: borough counts + full searchable list ──────────────────────
    with st.sidebar:
        st.subheader("Boroughs")
        for borough, color in _BOROUGH_COLORS.items():
            n = (df["boroname"] == borough).sum()
            st.markdown(
                f'<span style="color:{color};font-size:1.1rem">■</span> '
                f'**{borough}** — {n}',
                unsafe_allow_html=True,
            )
        st.divider()

        search = st.text_input("Search neighborhoods", placeholder="e.g. Greenpoint")
        if search:
            hits = df[df["ntaname"].str.contains(search, case=False, na=False)]
            if hits.empty:
                st.caption("No match.")
            else:
                for _, row in hits.iterrows():
                    color = _BOROUGH_COLORS.get(row["boroname"], MUTED)
                    st.markdown(
                        f'<span style="color:{color}">■</span> {row["ntaname"]} '
                        f'<span style="color:{MUTED};font-size:0.8rem">({row["boroname"]})</span>',
                        unsafe_allow_html=True,
                    )

    # ── Controls ────────────────────────────────────────────────────────────
    col_l, col_r = st.columns([3, 1])
    with col_r:
        show_nonresidential = st.checkbox(
            "Show parks, airports, cemeteries & institutional areas",
            value=False,
            help="ntatype 0 = residential (197). Others: parks (40), cemeteries (14), institutional (8), airports (2), Rikers (1).",
        )

    # ntatype '0' = residential neighbourhoods. All other codes are
    # parks, cemeteries, airports, institutional areas, and Rikers Island.
    df_map = df if show_nonresidential else df[df["ntatype"] == "0"]
    features_map = (
        geojson["features"] if show_nonresidential
        else [f for f in geojson["features"] if f["properties"].get("ntatype") == "0"]
    )
    geojson_map = {"type": "FeatureCollection", "features": features_map}

    # ── Map ─────────────────────────────────────────────────────────────────
    fig = px.choropleth_mapbox(
        df_map,
        geojson=geojson_map,
        locations="nta2020",
        featureidkey="properties.nta2020",
        color="boroname",
        color_discrete_map=_BOROUGH_COLORS,
        hover_name="ntaname",
        hover_data={
            "boroname": True,
            "nta2020":  True,
            "ntatype":  False,
        },
        labels={"boroname": "Borough", "nta2020": "NTA code"},
        mapbox_style="open-street-map",
        zoom=9.8,
        center={"lat": 40.70, "lon": -73.94},
        opacity=0.55,
        height=700,
    )
    fig.update_layout(
        paper_bgcolor=BACKGROUND,
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            title="Borough",
            bgcolor="rgba(14,17,23,0.85)",
            font=dict(color=TEXT),
            x=0.01,
            y=0.99,
            bordercolor="#374151",
            borderwidth=1,
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Full table ───────────────────────────────────────────────────────────
    with st.expander(f"All {len(df_map)} NTAs"):
        st.dataframe(
            df_map[["ntaname", "boroname", "ntatype", "nta2020"]]
            .sort_values(["boroname", "ntaname"])
            .rename(columns={
                "ntaname":  "Neighborhood",
                "boroname": "Borough",
                "ntatype":  "Type",
                "nta2020":  "NTA Code",
            }),
            use_container_width=True,
            hide_index=True,
        )


main()
