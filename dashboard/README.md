# Bikeshare Dashboard

A Streamlit dashboard for exploring DC Capital Bikeshare and NYC Citi Bike trip data side by side. Reads from the local Postgres database populated by the parent dbt project — see [../README.md](../README.md) for data pipeline setup.

## Pages

| Page | What it shows |
|---|---|
| **Overview** | Headline KPIs (rides, hours, stations) + member/casual and bike-type breakdowns |
| **Ride Activity** | Daily volume, duration metrics, night-owl rides — *coming next* |
| **Stations & Routes** | Top stations and popular routes per system — *coming next* |
| **Time Patterns** | Peak-hour and day-of-week distributions — *coming next* |
| **City Comparison** | Paired-bar comparison across every headline metric — *coming next* |

## Run

```bash
source ../.venv/bin/activate           # uses the project's existing dbt venv
pip install -r requirements.txt        # one-time
streamlit run Overview.py
```

Open `http://localhost:8501`. The sidebar shows all five pages; the header above each page has the system selector, month picker, and month-range toggle.

## How it reads from Postgres

Credentials come from `~/.dbt/profiles.yml` (the same file dbt uses) — no separate config. The SQLAlchemy engine is cached for the lifetime of the Streamlit session via `@st.cache_resource`; query results are cached per filter combination for one hour via `@st.cache_data(ttl=3600)`.

If a chart shows stale data after a dbt refresh, click the "⋮" menu (top-right) → "Clear cache" → rerun.

## Layout

```
dashboard/
├── Overview.py                  # Streamlit entry point + Overview page (filename = sidebar label)
├── pages/                       # Streamlit reads this folder for the sidebar nav
│   ├── 1_Ride_Activity.py
│   ├── 2_Stations_and_Routes.py
│   ├── 3_Time_Patterns.py
│   └── 4_City_Comparison.py
├── lib/                         # Helpers shared across pages
│   ├── db.py                    # SQLAlchemy engine + run_query
│   ├── filters.py               # Header filter widgets + Filters dataclass
│   ├── queries.py               # All SQL strings, each cached
│   ├── theme.py                 # Pastel palette, dark Plotly template
│   └── charts.py                # KPI tiles, donut chart, empty-state helpers
├── .streamlit/config.toml       # Dark theme config
├── requirements.txt
└── README.md
```

## Theme

- Dark background `#0E1117`, surface `#1A1D24`, text `#E6E6E6`.
- City identity: DC = periwinkle `#A5B4FC`, NYC = salmon `#FCA5A5`.
- Breakdown palette: mint, butter, lavender, rose. Defined in [lib/theme.py](lib/theme.py).
