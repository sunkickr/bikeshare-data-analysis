# Dashboard Features

Every shipped capability of the dashboard, with notes on what could subtly break it. Use this as the "what should still work?" checklist before merging changes — especially after refactors to `lib/`.

For architecture / module structure, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Cross-cutting (every page)

### F1. Global filter bar
- Renders at the top of every page: **System** dropdown · **Month** dropdown · **Multi-month** toggle.
- Filter values persist across page navigation via `p_*` keys in `st.session_state`.
- Default System: "Both". Default Month: most recent month present in `agg_rides_daily` (auto-detected, not hardcoded).
- Toggling **Multi-month** on swaps the single Month dropdown for **Start month** / **End month** dropdowns.
- **What could break:** any change to `lib/filters.py` that re-introduces `key=` on the widgets, or stops writing to `p_*`, will collapse the persistence. Test by setting filter, navigating to another page, and confirming both the *data* and the *displayed dropdown* still reflect the chosen month.

### F2. Dark theme + pastel chart palette
- Background `#0E1117`, surface `#1A1D24`, text `#E6E6E6` set in `.streamlit/config.toml`.
- Plotly charts use the `bikeshare_dark` template registered by `lib/theme.apply_plotly_defaults()`.
- DC = periwinkle, NYC = salmon; member/casual/classic/electric have stable colors via `SEGMENT_COLORS`.
- **What could break:** removing `apply_plotly_defaults()` from a page leaves its charts on Plotly's default white template; adding a chart helper that hardcodes colors instead of pulling from `lib/theme` will introduce visual inconsistency.

### F3. Side-by-side vs single-column layout
- When System filter is "Both", per-system sections render in 2 columns (DC left, NYC right).
- When System filter is "DC" or "NYC", the same sections collapse to a single full-width column.
- Driven by `system_columns(filters.systems)` in `lib/charts.py`.
- **What could break:** any page using `st.columns(2)` directly instead of `system_columns()` will keep showing two columns even after the user filters to one city.

### F4. Empty-state handling
- Any page section with zero rows for the selected filter renders a muted "No data for this selection" placeholder instead of crashing.
- Implemented via `empty_state()` helper called inside every per-system loop.
- **What could break:** new query functions that assume non-empty DataFrames (e.g., `df.iloc[0]` without an empty check) will raise on filters that match no data — e.g., Jan 2026 for systems with no January data.

### F5. Cache-backed performance
- Every query in `lib/queries.py` is wrapped in `@st.cache_data(ttl=3600)`. Second load of the same filter is sub-100ms.
- SQLAlchemy engine cached via `@st.cache_resource` — one engine per Streamlit session.
- **What could break:** adding a new query without the cache decorator runs raw SQL on every widget interaction. Calling `run_query` from inside a page module (instead of through a cached `lib/queries.py` function) sidesteps the cache.

## Overview page (`Overview.py`)

### F6. KPI tiles per system (Overview)
- Two KPI tiles per system: **Total Rides** (integer, comma-separated) and **Total Hours** (compact, e.g. "14.2k hrs").
- Each tile has a colored accent strip matching the system identity color.
- **What could break:** changing `format_int` / `format_hours` to a different output shape; changing the `kpi_tile` HTML structure.

### F7. Member vs Casual donut row
- Two donuts (one per system, when both selected). Labels rendered *outside* the donut on the dark background — light text on light pastels was unreadable, so we moved text out.
- DC donut uses periwinkle + first pastel; NYC donut uses salmon + first pastel.
- **What could break:** the `donut_chart` helper changing `textposition` back to "inside"; removing `automargin` would crop the labels.

### F8. Classic vs Electric donut row
- Same shape as F7, segmented by `rideable_type`.
- **What could break:** same as F7 — both donuts share the helper.

## Ride Activity page (`pages/1_Ride_Activity.py`)

### F9. Daily rides line chart
- Single Plotly chart with one line per system, sharing the x-axis (`started_date`).
- DC line periwinkle, NYC line salmon; `hovermode="x unified"` shows both values in one tooltip.
- **What could break:** switching to two side-by-side line charts loses the unified comparison; changes to `multi_system_line_chart` color mapping would lose city identity.

### F10. Duration KPI tiles per system
- Three tiles in the first row: **Avg Ride**, **Longest Ride**, **Shortest (Different Stations)**.
- Avg uses ride-volume-weighted average, not naive `AVG(avg_ride_minutes)`.
- Shortest filters `is_between_stations` AND `duration_minutes > 0` (data quality safety net).
- **What could break:** removing the `* total_rides` weight from the SQL gives misleading averages; removing the `duration_minutes > 0` filter exposes data-quality artifacts (zero-duration rides).

### F11. Activity callouts per system
- Three tiles in the second row: **Night Owls (12-5am)** with share %, **Busiest Day**, **Quietest Day**.
- Busiest / quietest dates derived from `agg_rides_daily` by ranking, then displayed as "MMM DD" with ride count caption.
- **What could break:** changes to the `busiest_and_quietest_day` query that drop the `kind` column ('busiest' / 'quietest') break the lookup keys used by the page.

### F12. Member vs Casual stacked-bar timeseries
- Per system, one stacked bar per `started_date` with member / casual segments.
- Segment colors from `SEGMENT_COLORS` in theme.
- **What could break:** unsorted segment order would flicker between renders; the `stacked_bar_timeseries` helper explicitly sorts segments alphabetically to keep the color order stable.

### F13. Classic vs Electric stacked-bar timeseries
- Same structure as F12, segmented by `rideable_type`.
- **What could break:** same as F12.

## Stations & Routes page (`pages/2_Stations_and_Routes.py`)

### F23. Top stations & routes geographic map
- One Plotly mapbox map per system, rendered at the **top** of the page above the existing bar charts. Layout collapses to a single full-width map when the System filter is "DC" or "NYC" only.
- Four z-ordered layers per map:
  1. **Dim background**: every station in `dim_stations` for that system, rendered as small slate dots (~840 for DC, ~2,300 for NYC). Provides geographic context for the highlighted markers.
  2. **Route lines**: top 5 routes drawn between station coordinates, line width proportional to ride count (clamped 1.5 → 6).
  3. **End station markers**: top 10 end stations, light orange (`MAP_END_COLOR`), size proportional to ride count (clamped 10 → 28).
  4. **Start station markers**: top 10 start stations, mint (`MAP_START_COLOR`), same size scaling — on top so they read as the primary highlight.
- Basemap: `carto-darkmatter` (no Mapbox API token required).
- Initial center + zoom per system: DC at `(38.92, -77.03)`, NYC at `(40.73, -73.99)`, both at zoom 11. Defined in `lib/theme.MAP_CENTER` and `MAP_ZOOM`.
- Hover tooltips: dim dots show just the station name, highlighted markers show name + start/end ride count, route lines show "Start → End: N rides".
- **What could break:**
  - **Removing or renaming any of the four geo queries** (`all_stations_geo`, `top_start_stations_geo`, `top_end_stations_geo`, `top_routes_geo`) — the page would error on import.
  - **Changing the LEFT JOIN to dim_stations in the geo queries** to an INNER JOIN — would drop top stations that aren't yet registered in `dim_stations`, silently shrinking the visible markers.
  - **Reordering trace additions in `station_route_map`** — z-order matters: dim background must go first so the highlights sit visually on top of it.
  - **Per-route trace explosion in the legend**: each route is its own Plotly trace (Scattermapbox can't do per-segment line width otherwise). The legend stays clean only because every route trace shares `legendgroup="routes"` with `showlegend=False`, and a single placeholder trace at the end provides the visible legend entry. Removing the placeholder removes the "Top routes" legend entry; removing the `legendgroup` floods the legend with 5 individual route entries.
  - **Plotly upgrade past 5.x:** `go.Scattermapbox` is deprecated in favor of `go.Scattermap` in Plotly 6. The chart helper will need to migrate.

### F14. Top 10 start stations per system
- Horizontal bar chart per system, side by side. Y-axis = station name, X-axis = ride count.
- Highest-volume station at top of chart (data sorted ascending so Plotly draws it last).
- Ride counts shown as compact text outside each bar.
- **What could break:** sorting the input DataFrame descending would invert the chart; removing `cliponaxis=False` would clip text labels on long bars.

### F15. Top 10 end stations per system
- Symmetric to F14 on `end_station_name`.

### F16. Top 5 routes per system
- Horizontal bar chart with `start_station_name → end_station_name` labels.
- **Round trips excluded** (`start_station_name <> end_station_name` in the query). The map and the bar chart now agree — both show only directional routes. This makes the top-N a list of actual journeys, not a list of which stations are the busiest hubs.
- **What could break:** re-introducing round trips would surface hub stations as "routes" and inflate the top-N with start=end pairs.

## Time Patterns page (`pages/3_Time_Patterns.py`)

### F17. Rides by hour of day
- 24-bar distribution per system, side by side.
- X-axis is the integer hour (0-23); Y-axis is ride count. Single bar color = system identity.
- **What could break:** changing the X-axis to formatted strings ("12am") without `preserve_x_order=True` lets Plotly alphabetize the labels.

### F18. Rides by day of week
- 7-bar distribution per system, side by side.
- X-axis labels are day names; order is preserved by passing `preserve_x_order=True` to the helper (driven by `started_dow` in the SQL ORDER BY).
- **What could break:** removing the `ORDER BY started_dow` from the query lets the DataFrame come back in undefined order, scrambling the X-axis.

### F19. Busiest / quietest day callouts (mirrored)
- Same two KPI tiles per system as F11 on Ride Activity. Shares the `busiest_and_quietest_day` cache entry, so when the filter is unchanged the second page hits the cache instantly.
- **What could break:** renaming the shared query function in `lib/queries.py` without updating both pages breaks one of them.

## City Comparison page (`pages/4_City_Comparison.py`)

### F20. Page-level system filter override
- The System dropdown is *ignored* on this page — comparison always shows both systems.
- An `st.info` banner notifies the user when their filter is being overridden.
- **What could break:** removing the explicit `ALL_SYSTEMS` constant or passing `filters.systems` to `city_summary` would cause the page to mis-render when the user has filtered to one city.

### F21. 12 paired comparison tiles
- 3 rows × 4 columns of `comparison_tile` widgets. Each tile shows DC and NYC values for one metric, with bar widths scaled to the larger of the two.
- Metrics grouped: **Volume** (Total Rides, Total Hours, Avg Daily Rides, Busiest Day Rides), **Network + duration** (Unique Stations, Active Stations, Rides / Active Station, Avg Ride Min), **Composition** (Member / Classic / Night Owl / Round Trip Share).
- Bar identity colors: DC periwinkle, NYC salmon.
- **What could break:** the `city_summary` query schema change (renamed column, added/removed metric) without updating the `_derive_metrics` mapping in the page; broken share formulas if total_rides is zero (handled by `_safe_div` returning None).

### F22. Single source query for all comparison metrics
- A single `city_summary` query returns one row per system with every column the page needs (12 metrics). Three CTEs joined: `daily`, `agg`, `stations`, `active`.
- Active Stations metric requires a `COUNT(DISTINCT)` over `fct_rides` — the only `fct_rides` scan on this page.
- **What could break:** breaking the query into multiple smaller queries means multiple cache entries to keep coherent on every render.

## DC Neighborhood Analysis page (`pages/10_DC_Neighborhood_Analysis.py`)

### F24. DC choropleth map with boundary toggle
- Choropleth map of DC colored by the selected metric, with a radio toggle between two boundary definitions: **OSM Neighborhoods (117)** and **Planning Clusters (39)**.
- Metric selector in the sidebar: total rides, rides/km², rides/1k residents, member %, avg trip duration.
- Color scale clamped to the p05–p95 range so outlier zones don't wash out the rest of the map.
- Clicking a zone outlines it in white and populates a detail card in the sidebar.
- Basemap: `open-street-map` (light background chosen to make colored polygons pop; differs intentionally from the `carto-darkmatter` basemap used on Stations & Routes).
- **What could break:** the page reads GeoJSON from `data/geo/dc_neighborhoods_osm.geojson` and `data/geo/dc_clusters.geojson` via absolute path relative to the page file — moving the page file or the `data/geo/` folder breaks the load. The `_load_geojson` cache has no TTL (files are static); the `_load_data` query cache is `ttl=3600`.

### F25. Click-to-drill neighborhood detail card
- Selecting a zone (by map click or table row click) shows a detail card in the sidebar with 8 metrics: total rides, member %, rides/km², rides/1k residents, avg duration, area, population, and median household income.
- Selection is stored in `st.session_state["nbhd_selected"]`; clearing it via the ✕ button resets both the sidebar card and the white polygon outline in a single rerun.
- **What could break:** the zone's `zone_id` in the data must match the GeoJSON feature's property key exactly (e.g. `neighborhood_name` for OSM, `cluster_id` for clusters). A seed or GeoJSON update that renames or reformats these keys silently stops the outline and detail card from appearing for affected zones.

### F26. NYC Neighborhoods exploration page (`pages/5_NYC_Neighborhoods.py`)
- Temporary exploration page showing 262 NYC Neighborhood Tabulation Areas (NTAs) from NYC Open Data, color-coded by borough.
- **Not connected to the database** — fetches GeoJSON from `data.cityofnewyork.us` at startup, cached for 24 hours (`ttl=86_400`). Fails gracefully with `st.error` on `URLError`.
- Sidebar shows borough counts and a search box to filter neighborhoods by name.
- A checkbox toggles visibility of non-residential areas (parks, airports, cemeteries, Rikers).
- Does not use the global filter bar or `p_*` session state.
- **What could break:** the NYC Open Data endpoint changing its schema (field names `nta2020`, `ntaname`, `boroname`, `ntatype`) would silently produce empty columns. Upgrading past Plotly 5.x requires migrating `choropleth_mapbox` → `choropleth_map`.

---

## Reference: query → page mapping

| Query | Used by |
|---|---|
| `overview_kpis` | F6 |
| `unique_station_count` | F6 |
| `member_casual_breakdown` | F7 |
| `rideable_type_breakdown` | F8 |
| `daily_rides_over_time` | F9 |
| `duration_stats` | F10, F11 (night-owl share) |
| `shortest_ride_between_stations` | F10 |
| `busiest_and_quietest_day` | F11, F19 |
| `daily_member_casual` | F12 |
| `daily_rideable_type` | F13 |
| `top_start_stations` | F14 |
| `top_end_stations` | F15 |
| `top_routes` | F16 |
| `all_stations_geo` | F23 |
| `top_start_stations_geo` | F23 |
| `top_end_stations_geo` | F23 |
| `top_routes_geo` | F23 |
| `rides_by_hour` | F17 |
| `rides_by_dow` | F18 |
| `city_summary` | F20, F21, F22 |
| `_load_data` (inline, `agg_rides_by_neighborhood` or `agg_rides_by_cluster`) | F24, F25 |
| NYC Open Data fetch (external, no DB) | F26 |
