"""Neighborhood Rankings — fun "superlative" awards for DC neighborhoods.

Eight awards (Most Total Rides, Ebike Lovers, Tourist Trap, …), each crowning one
neighborhood for the most recent month of data, with a tagline, three runner-ups,
and a map centered on the winner. Built to spark buzz: residents love seeing their
neighborhood top a list.

DC-only by design (neighborhood marts exist only for Capital Bikeshare). The page
is isolated — it does NOT use the global header filter bar (no system selector, no
month picker): rankings always reflect MAX(started_month), refreshing each dbt run.

Data:   lib.queries.neighborhood_rankings  → analytics_marts.agg_rides_by_neighborhood
Map:    data/geo/dc_neighborhoods_osm.geojson (id property: neighborhood_name)
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from lib import queries
from lib.charts import empty_state, format_int, ranking_highlight_map
from lib.theme import MUTED, PASTEL_PALETTE, TEXT, apply_plotly_defaults

st.set_page_config(page_title="Neighborhood Rankings", page_icon="🏆", layout="wide")
apply_plotly_defaults()

_REPO_ROOT = Path(__file__).parent.parent.parent
_GEOJSON_PATH = _REPO_ROOT / "data" / "geo" / "dc_neighborhoods_osm.geojson"
_FEATURE_KEY = "properties.neighborhood_name"
_RUNNER_UPS = 3

# ═════════════════════════════════════════════════════════════════════════════
# RANKING ELIGIBILITY — edit these to explore. All ranking policy lives here and
# is applied on the page (see main()), so changing a number or a list updates the
# whole page at once. A neighborhood is ranked for the month when it has strictly
# more than MIN_RIDES rides AND more than MIN_POPULATION residents — UNLESS it is
# force-included below, and never if it is excluded below.
# ═════════════════════════════════════════════════════════════════════════════
MIN_RIDES = 600          # rides started in the neighborhood that month
MIN_POPULATION = 1000     # residents (set to 0 to disable the population floor)

# Always exclude these neighborhoods by name — too small, or mostly downtown
# offices/commercial rather than a place residents identify with. Add or remove
# entries freely; names must match analytics_marts.agg_rides_by_neighborhood
# (.neighborhood_name) exactly, or the entry silently does nothing.
EXCLUDED_NEIGHBORHOODS = {
    "Blagden Alley-Naylor Court Historic District",
    "Southwest Employment Area",
    "Chinatown",
    "Downtown East",
    "Golden Triangle",
    "Cardozo/Shaw",
    "Greater U Street Historic District",
    "Mount Vernon Square",
}

# Always INCLUDE these by name even if they fall below the thresholds above
# (small-but-notable destinations worth ranking). Same exact-name rule as the
# exclude list. If a name is in both lists, the exclude wins.
INCLUDED_NEIGHBORHOODS = {
    "The Wharf",
    "Capitol View",
}


# ── Value formatting ─────────────────────────────────────────────────────────
def _fmt_count(v: float) -> str:
    return format_int(v)


def _fmt_pct(v: float) -> str:
    return f"{v:.1f}%"


def _fmt_ratio(v: float) -> str:
    return f"{v:,.1f}"


def _fmt_per_resident(v: float) -> str:
    return f"{v:,.2f}"


# ── Superlative config ───────────────────────────────────────────────────────
# Order matters: sections are awarded top-to-bottom, and a neighborhood can win
# at most one (winner-only exclusivity). Accent colors cycle the shared palette.
@dataclass(frozen=True)
class Superlative:
    title: str
    tagline: str
    metric: str           # column in the rankings DataFrame
    ascending: bool       # True = smaller value wins (e.g. lowest member %)
    unit: str             # short label shown next to the value
    fmt: Callable[[float], str]   # value formatter


SUPERLATIVES: list[Superlative] = [
    Superlative(
        "Superior Bike Neighborhood",
        "Probably the biggest, densest neighborhood — can't deny them!",
        "total_rides", False, "rides", _fmt_count,
    ),
    Superlative(
        "Bikeshare-Addicted Residents",
        "The residents of this neighborhood just can't get enough!",
        "rides_per_resident", False, "rides / resident", _fmt_per_resident,
    ),
    Superlative(
        "Tourist Trap!",
        "Sorry, can't argue with the data…",
        "member_pct", True, "member rides", _fmt_pct,
    ),
    Superlative(
        "Most in Need of More Bike Stations!",
        "You may never find a Cabi e-bike here…",
        "rides_per_station", False, "rides / station", _fmt_ratio,
    ),
    Superlative(
        "The Night Owl Neighborhood",
        "After a long night out all they want to do is bike!",
        "night_owl_pct", False, "rides 12–5am", _fmt_pct,
    ),
    Superlative(
        "Most Laid Back",
        "We bike for fun here! It's about the journey, not the destination…",
        "round_trip_pct", False, "round-trip rides", _fmt_pct,
    ),
    Superlative(
        "Ride Density Champion",
        "What they lack in size they make up in rides!",
        "rides_per_km2", False, "rides / km²", _fmt_ratio,
    ),
    Superlative(
        "Ebike Lovers",
        "They've got places to be — no time for slow bikes!",
        "electric_pct", False, "e-bike rides", _fmt_pct,
    ),
]


@st.cache_data(show_spinner=False)
def _load_geojson() -> dict:
    """OSM neighborhood boundaries. No TTL — the file is a frozen static snapshot."""
    return json.loads(_GEOJSON_PATH.read_text())


@dataclass
class Award:
    spec: Superlative
    accent: str
    winner: pd.Series
    runners: pd.DataFrame


def _compute_awards(df: pd.DataFrame) -> list[Award]:
    """Greedy winner-only-exclusive assignment.

    Process superlatives in list order. For each, rank eligible neighborhoods by
    the metric (ties broken by total_rides, so the busier neighborhood wins), take
    the first not already a winner as this award's winner, then the next three rows
    as runner-ups. Runner-ups are NOT de-duplicated across sections — a neighborhood
    that won one award can still place as a runner-up in another.
    """
    taken: set[str] = set()
    awards: list[Award] = []
    for i, spec in enumerate(SUPERLATIVES):
        ranked = df.sort_values(
            [spec.metric, "total_rides"],
            ascending=[spec.ascending, False],
            kind="stable",
        ).reset_index(drop=True)

        winner_pos = next(
            (pos for pos, name in enumerate(ranked["neighborhood_name"]) if name not in taken),
            None,
        )
        if winner_pos is None:        # every eligible zone already won — shouldn't happen
            continue
        winner = ranked.iloc[winner_pos]
        taken.add(winner["neighborhood_name"])

        runners = ranked.drop(index=winner_pos).head(_RUNNER_UPS)
        accent = PASTEL_PALETTE[i % len(PASTEL_PALETTE)]
        awards.append(Award(spec=spec, accent=accent, winner=winner, runners=runners))
    return awards


def _render_award(award: Award, geojson: dict) -> None:
    spec, accent, winner = award.spec, award.accent, award.winner
    value = spec.fmt(winner[spec.metric])

    left, right = st.columns([1.4, 1], gap="large")

    with left:
        st.markdown(
            f'<div style="color:{accent};font-size:1.05rem;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.06em">{spec.title}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="color:{TEXT};font-size:2.6rem;font-weight:700;'
            f'line-height:1.1;margin:6px 0 2px">{winner["neighborhood_name"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="color:{accent};font-size:1.1rem;font-weight:600">'
            f'{value} <span style="color:{MUTED};font-weight:400">{spec.unit}</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="color:{MUTED};font-style:italic;font-size:0.95rem;'
            f'margin-top:8px">{spec.tagline}</div>',
            unsafe_allow_html=True,
        )

        rows = ""
        for rank, (_, r) in enumerate(award.runners.iterrows(), start=2):
            rows += (
                f'<div style="display:flex;justify-content:space-between;'
                f'color:{TEXT};font-size:0.9rem;padding:2px 0">'
                f'<span><span style="color:{MUTED}">{rank}.</span> {r["neighborhood_name"]}</span>'
                f'<span style="color:{MUTED}">{spec.fmt(r[spec.metric])}</span></div>'
            )
        st.markdown(
            f'<div style="margin-top:14px">'
            f'<div style="color:{MUTED};font-size:0.75rem;text-transform:uppercase;'
            f'letter-spacing:0.05em;margin-bottom:4px">Runner-ups</div>{rows}</div>',
            unsafe_allow_html=True,
        )

    with right:
        fig = ranking_highlight_map(
            geojson,
            feature_key=_FEATURE_KEY,
            zone_id=winner["neighborhood_name"],
            accent=accent,
            center_lat=float(winner["centroid_lat"]),
            center_lng=float(winner["centroid_lng"]),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _divider() -> None:
    st.markdown(
        f'<hr style="border:none;border-top:2px dashed {MUTED};opacity:0.4;margin:8px 0 24px">',
        unsafe_allow_html=True,
    )


def main() -> None:
    st.title("🏆 Neighborhood Rankings")

    # Fetch the full month (no SQL threshold), then apply all eligibility policy
    # here so the include/exclude lists and thresholds act in one place.
    full = queries.neighborhood_rankings(min_population=0, min_rides=0)
    meets_rides = full["total_rides"] > MIN_RIDES
    meets_pop = True if MIN_POPULATION <= 0 else (full["population"] > MIN_POPULATION)
    forced = full["neighborhood_name"].isin(INCLUDED_NEIGHBORHOODS)
    blocked = full["neighborhood_name"].isin(EXCLUDED_NEIGHBORHOODS)
    df = full[((meets_rides & meets_pop) | forced) & ~blocked].reset_index(drop=True)
    if df.empty:
        empty_state("No neighborhoods meet the ranking thresholds yet.")
        st.stop()

    month = pd.to_datetime(df["month"].iloc[0])
    threshold_txt = f"more than {MIN_RIDES:,} rides"
    if MIN_POPULATION > 0:
        threshold_txt += f" and {MIN_POPULATION:,} residents"
    st.caption(
        f"Rankings for {month:%B %Y} · DC neighborhoods with {threshold_txt} "
        f"({len(df)} qualify)"
    )
    st.divider()

    geojson = _load_geojson()
    awards = _compute_awards(df)
    for i, award in enumerate(awards):
        _render_award(award, geojson)
        if i < len(awards) - 1:
            _divider()


main()
