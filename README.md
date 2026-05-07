# Bikeshare Data Analysis

A local analytics pipeline that ingests monthly trip data from multiple US bikeshare systems
(Capital Bikeshare, Citi Bike) into Postgres and transforms it with dbt into analysis-ready tables.

## What it produces

| Table | Description |
|---|---|
| `analytics_marts.fct_rides` | One row per ride — duration, hour, day-of-week, flags. Incremental. |
| `analytics_marts.dim_stations` | One row per unique station, with most-recent name and coordinates. |
| `analytics_marts.agg_rides_daily` | Daily ride counts and duration metrics, sliced by system / member type / bike type. |

---

## Prerequisites

| Tool | Version |
|---|---|
| PostgreSQL | 16 (via Homebrew: `brew install postgresql@16`) |
| Python | 3.11+ |
| dbt-postgres | installed in `.venv` (see setup below) |

---

## One-time setup

### 1. Postgres database and user

```sql
-- run as a superuser, e.g.:  psql -U postgres
CREATE USER dbt_user WITH PASSWORD 'dbt_password';
CREATE DATABASE bikeshare OWNER dbt_user;
\c bikeshare
CREATE SCHEMA raw AUTHORIZATION dbt_user;
GRANT ALL ON SCHEMA raw TO dbt_user;
```

### 2. dbt profile

dbt reads credentials from `~/.dbt/profiles.yml` (outside the repo — never committed).

```yaml
# ~/.dbt/profiles.yml
bikeshare:
  target: dev
  outputs:
    dev:
      type: postgres
      host: localhost
      port: 5432
      user: dbt_user
      password: dbt_password
      dbname: bikeshare
      schema: analytics
      threads: 4
      keepalives_idle: 0
```

### 3. Python environment and dbt packages

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install dbt-postgres

cd bikeshare
dbt deps          # installs dbt_utils from packages.yml
```

---

## Adding data

Drop monthly CSV files into `data/`. The filename determines which system they belong to:

| Filename pattern | System |
|---|---|
| `*capitalbikeshare-tripdata*.csv` | Capital Bikeshare |
| `*citibike-tripdata*.csv` | Citi Bike (NYC core and Jersey City `JC-` prefix both work) |

Files that have already been loaded are tracked by filename in the raw tables and skipped
automatically on subsequent runs — so dropping a file into `data/` and re-running is always safe.

---

## Running the pipeline

### Full automated refresh (recommended)

```bash
scripts/refresh_pipeline.sh
```

This runs both steps in order and writes a timestamped log to `logs/`:

1. Loads any new CSVs from `data/` into the raw Postgres tables.
2. Runs `dbt build` (models + tests together).

Exit code is non-zero if any step fails, so it works as a cron target.

### Cron setup (optional)

To refresh automatically, add a line via `crontab -e`:

```
0 6 * * 1 /Users/davidkoenitzer/bikeshare-data-analysis/scripts/refresh_pipeline.sh
```

This runs every Monday at 06:00. Adjust the schedule as needed.

---

## Manual dbt commands

Run all of these from the `bikeshare/` directory (or prefix with `cd bikeshare &&`).

```bash
# Build all models and run all tests (the normal workflow)
dbt build

# Build only — skips tests
dbt run

# Test only — useful after a data fix
dbt test

# Rebuild a single model and its tests
dbt build --select fct_rides

# Rebuild a model plus every model downstream of it
dbt build --select fct_rides+

# Force a full rebuild of the incremental fact table (drops and recreates)
dbt run --select fct_rides --full-refresh

# Check whether source data is fresh (warns/errors based on freshness config)
dbt source freshness

# Generate and browse the lineage documentation
dbt docs generate
dbt docs serve    # opens at http://localhost:8080
```

---

## Project structure

```
bikeshare-data-analysis/
├── data/                        # Raw monthly CSV files (not committed)
├── logs/                        # Pipeline run logs (not committed)
├── scripts/
│   ├── load_raw_csv.sh          # Load a single CSV into raw.<system>_trips
│   ├── load_unprocessed_csvs.sh # Idempotent: load only new files from data/
│   └── refresh_pipeline.sh      # Orchestrator — cron target
└── bikeshare/                   # dbt project
    ├── dbt_project.yml
    ├── packages.yml
    └── models/
        ├── staging/
        │   ├── capitalbikeshare/  # stg_capitalbikeshare__trips (view)
        │   └── citibike/          # stg_citibike__trips (view)
        ├── intermediate/
        │   └── rides/             # int_rides__unioned — unions all systems (view)
        └── marts/
            └── rides/             # fct_rides (incremental table)
                                   # dim_stations (table)
                                   # agg_rides_daily (table)
```

### Model layers

- **staging** — one model per source system. Casts types, renames columns, adds the `system`
  column. Materialized as views (always fresh, no storage cost).
- **intermediate** — unions all staging models into a single, system-agnostic grain.
  Materialized as views (cheap to rebuild, easy to inspect in psql).
- **marts** — business-meaningful tables queried by dashboards and ad-hoc analysis.
  `fct_rides` is incremental (only processes new rows on each run); the others do a full
  rebuild from the already-filtered fact table, which is fast.

---

## Adding a new bikeshare system

1. Create `models/staging/<system>/stg_<system>__trips.sql` — cast columns, add `system = '<system>'::text`.
2. Create the matching `_<system>__sources.yml` and `_<system>__models.yml`.
3. Add a `SELECT * FROM {{ ref('stg_<system>__trips') }}` + `UNION ALL` block in `int_rides__unioned.sql`.
4. Extend `scripts/load_unprocessed_csvs.sh`: add a filename pattern in `system_for_file()` and
   an `already_loaded <system>` call near the top.

No changes needed to `fct_rides`, `dim_stations`, or `agg_rides_daily` — they read from the
intermediate union layer and are already system-agnostic.
