# Dashboard Architecture

Streamlit-based analytics UI for the bikeshare project. Reads from the dbt-produced `analytics_marts` schema in local Postgres. Lives entirely under `dashboard/` — additive to the broader project, no modifications to the dbt pipeline or repo root.

## High-level diagram

```
┌───────────────────────────────────────────────────────────────────┐
│ Browser (http://localhost:8501)                                   │
│   ▲                                                               │
│   │ WebSocket                                                     │
└───┼───────────────────────────────────────────────────────────────┘
    │
┌───┴───────────────────────────────────────────────────────────────┐
│ Streamlit server (streamlit run Overview.py)                      │
│                                                                   │
│   Overview.py ─────┐                                              │
│   pages/*.py ──────┤── render_header_filters() → Filters dataclass│
│                    └── per-page queries.py calls                  │
│                          │                                        │
│   lib/                   ▼                                        │
│   ├── theme.py     ┌──────────────┐                               │
│   ├── filters.py   │ lib/queries  │ ── @st.cache_data(ttl=1h) ──┐ │
│   ├── charts.py    └──────────────┘                             │ │
│   ├── queries.py         │                                      │ │
│   └── db.py              ▼                                      │ │
│                    ┌──────────────┐                             │ │
│                    │ lib/db       │ ── @st.cache_resource ────┐ │ │
│                    └──────────────┘   (SQLAlchemy engine)     │ │ │
└───────────────────────────────────────────────────────────────┼─┼─┘
                                                                ▼ ▼
                                ┌───────────────────────────────────┐
                                │ Postgres (localhost:5432)         │
                                │   analytics_marts.fct_rides       │
                                │   analytics_marts.dim_stations    │
                                │   analytics_marts.agg_rides_daily │
                                └───────────────────────────────────┘
```

## Directory layout

```
dashboard/
├── Overview.py              # Streamlit entry point (also page #1 in sidebar)
├── pages/
│   ├── 1_Ride_Activity.py
│   ├── 2_Stations_and_Routes.py
│   ├── 3_Time_Patterns.py
│   └── 4_City_Comparison.py
├── lib/
│   ├── db.py                # SQLAlchemy engine (cached) + run_query helper
│   ├── filters.py           # Header filter widgets + Filters dataclass
│   ├── queries.py           # Every SQL query the dashboard runs, all cached
│   ├── theme.py             # Colors, Plotly dark template, system identity colors
│   └── charts.py            # Chart wrappers + KPI tile + comparison tile helpers
├── .streamlit/config.toml   # Dark theme + headless server settings
├── requirements.txt         # Pinned Python deps
├── README.md                # How to run + theme legend
├── ARCHITECTURE.md          # This file
└── FEATURES.md              # Capabilities catalog (for feature-check)
```

## Conventions and invariants

These are the rules that other dashboard code relies on. Breaking them silently degrades the app.

### Data source
- **All queries hit `analytics_marts.*` only.** Never read from `raw.*` or `analytics.*` directly. The marts layer is the contract between dbt and the dashboard.
- **`fct_rides` is hit by a small set of queries:** `shortest_ride_between_stations`, `top_start_stations`, `top_end_stations`, `top_routes`, `top_start_stations_geo`, `top_end_stations_geo`, `top_routes_geo`, `rides_by_hour`, `rides_by_dow`, and the `active_stations` CTE inside `city_summary`. Everything else uses `agg_rides_daily` or `dim_stations` for speed.
- **`dim_stations` is the source of truth for station coordinates.** `fct_rides.start_lat` / `start_lng` carry per-ride coordinates that are noisy for DC (GPS jitter — ~66 unique lat values per `station_id`). Any query that needs a stable lat/lng must LEFT JOIN `dim_stations` on `(system, station_id)` rather than aggregating `fct_rides` coordinates. The four `*_geo` queries follow this pattern; `all_stations_geo` reads `dim_stations` directly.
- **`started_date` / `started_month` is the canonical time bucket.** Never use `ended_at` for filtering — rides spilling into the next month belong to the month they *started*.

### Module layering
```
pages ──→ lib.filters, lib.queries, lib.charts, lib.theme
lib.queries ──→ lib.db
lib.charts ──→ lib.theme
lib.filters ──→ lib.db (via get_available_months)
```
- **Pages never import each other.** Shared logic moves into `lib/`.
- **Pages never write raw SQL.** All SQL lives in `lib/queries.py`, every function is cached.
- **`lib/db.py` is the only module that talks to SQLAlchemy.** Pages and other lib modules go through `run_query`.

### Filter state (Streamlit multipage app)
- **Source of truth = `p_*` keys in `st.session_state`.** These are user-owned (explicit writes) so they survive page navigation. Streamlit prunes widget-bound state on navigation; only direct `st.session_state["..."] = value` writes persist.
- **Widgets render without `key=`.** Each render, `lib/filters.py` reads `p_*`, passes the matching `index=` / `value=` to the widget, then writes the widget's return back to `p_*`. Single source of truth, no widget-state race.
- The keys are: `p_system`, `p_month`, `p_range_start`, `p_range_end`, `p_is_range`.

### Caching layers
- **`@st.cache_resource`** wraps the SQLAlchemy engine in `lib/db.py`. One engine per Streamlit session.
- **`@st.cache_data(ttl=3600)`** wraps every query function in `lib/queries.py`. Cache key is the function's args (`systems`, `month_start`, `month_end`, optional `limit`). TTL = 1 hour because dbt rebuilds are scheduled weekly.
- **Streamlit reruns the whole script on every interaction.** Caching is what keeps that cheap. A new query function added without `@st.cache_data` will re-execute every widget change.

### Visual identity
- **DC = periwinkle `#A5B4FC`, NYC = salmon `#FCA5A5`.** Used everywhere a city is named. Defined in `lib/theme.py` as `DC_COLOR` / `NYC_COLOR` and bound to system slugs via `SYSTEM_COLOR`.
- **Pastel palette** for breakdowns (member/casual, classic/electric): mint, butter, lavender, rose. Specific assignments in `lib/theme.SEGMENT_COLORS`.
- **Map palette** (Stations & Routes only): `MAP_BASE_COLOR` (slate dim background), `MAP_START_COLOR` (mint, top starts), `MAP_END_COLOR` (light orange, top ends), `MAP_ROUTE_COLOR` (muted gray, routes). Plus `MAP_CENTER` (per-system initial lat/lng) and `MAP_ZOOM`. Defined in `lib/theme.py`.
- **Dark base:** background `#0E1117`, surface `#1A1D24`, text `#E6E6E6`.
- **Plotly template** `bikeshare_dark` registered globally by `lib/theme.apply_plotly_defaults()`. Every page calls this once at the top.

### Layout primitives
- **`system_columns(filters.systems)`** returns the right column count for the current filter — 2 columns when both systems selected, 1 column when one is filtered. Pages use this for every side-by-side render.
- **`empty_state(msg)`** renders a muted "no data" placeholder. Every per-system loop calls it when its subset is empty, so the page never crashes on a system with zero rows in the filter window.
- **`system_header(system)`** renders the colored "DC" / "NYC" label that prefixes each per-system column.

### Filter contract
The `Filters` dataclass is the shared input to every page section:
- `systems: tuple[str, ...]` — dbt slug values, e.g. `("capitalbikeshare", "citibike")`
- `month_start: date` — first-of-month
- `month_end: date` — first-of-month, inclusive

Queries treat `month_start == month_end` as a single-month filter and `month_start < month_end` as a range. The SQL pattern is `started_date >= :month_start AND started_date < (DATE :month_end + INTERVAL '1 month')` so the end month is fully included.

## Data flow per page render

1. Streamlit runs the page script top-to-bottom (`Overview.py` or `pages/N_*.py`).
2. The page calls `apply_plotly_defaults()` (idempotent — template registration).
3. The page calls `render_header_filters()` from `lib/filters`. This:
   - Reads `p_*` from `st.session_state` (or initializes from defaults if missing).
   - Renders the System / Month / Multi-month widgets in a single row at the top.
   - Returns a `Filters` dataclass.
4. The page calls one or more cached functions from `lib/queries`. Cache hit returns immediately; cache miss runs SQL via `lib/db.run_query()`.
5. The page passes the resulting DataFrames into helpers from `lib/charts` to render KPI tiles, donuts, line/bar charts, or comparison tiles.
6. On filter change or page navigation, Streamlit reruns from step 1.

## Postgres connection details

- Credentials are read from `~/.dbt/profiles.yml` at engine creation time. No credentials in the dashboard repo.
- Profile: `bikeshare`, target: `dev`. Same source of truth dbt uses.
- Connection string built dynamically in `lib/db._read_profile()`.
- `pool_pre_ping=True` on the engine — handles Postgres restarts mid-session.

## Known limitations

- **Streamlit 1.41.1 mapbox zoom bug** ([streamlit#10346](https://github.com/streamlit/streamlit/issues/10346)) — pan and click on the Stations & Routes map work, but programmatic / scroll-wheel zoom can be janky. Mitigated by setting a sensible initial zoom (`MAP_ZOOM = 11`) per system. Upgrading Streamlit past 1.42+ resolves it but requires re-testing the rest of the app.
- **Plotly `Scattermapbox` is deprecated in Plotly 6.x** in favor of `go.Scattermap` + MapLibre. We're pinned to Plotly 5.24.1 where `Scattermapbox` still works. A future Plotly upgrade will require migrating `station_route_map` in `lib/charts.py`.

## Python environment

- Uses the project's existing `.venv` at the repo root (Python 3.13).
- Dashboard adds: `streamlit==1.41.1`, `plotly==5.24.1`, `pandas==2.2.3`, `sqlalchemy==2.0.36`, `psycopg2-binary==2.9.10`.
- dbt-postgres `1.9.1` and dbt-core `1.11.11` (stable pair) coexist in the same venv. There's a known protobuf version conflict between Streamlit and dbt-common but it doesn't affect runtime behavior.
