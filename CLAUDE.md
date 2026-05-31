# CLAUDE.md

Project context for Claude Code agents working on this dbt project.
For full setup instructions, see [README.md](README.md).

## What this project is

A local-Postgres dbt project ingesting monthly bikeshare CSVs (Capital Bikeshare, Citi Bike) and modeling them into analysis-ready marts. Postgres is local on purpose — this is a learning project, not a production warehouse. Do not suggest migrating to Snowflake/BigQuery.

## Where things live

| Path | Purpose |
|---|---|
| `bikeshare/` | The dbt project root — `dbt_project.yml`, `models/`, `packages.yml` |
| `bikeshare/models/staging/<system>/` | One model per source system. Views. Casts types, adds `system` column. |
| `bikeshare/models/intermediate/rides/` | `int_rides__unioned` — unions all staging models. View. |
| `bikeshare/models/marts/rides/` | `fct_rides` (incremental), `dim_stations`, `agg_rides_daily` |
| `scripts/` | CSV loaders and the cron-targetable `refresh_pipeline.sh` |
| `data/` | Raw monthly CSVs. Gitignored. |
| `logs/` | Pipeline run output. Gitignored. |

## Conventions

- Layering: staging (per-system, views) → intermediate (unioned, view) → marts (tables, mostly incremental). Do not skip layers.
- Every staging model adds a literal `system = '<system>'::text` column so downstream models stay system-agnostic.
- Time-bucket all analytics by `started_at`, not `ended_at`. A ride that starts on Jan 31 23:50 and ends Feb 1 00:15 is a January ride for our purposes.
- `fct_rides` is materialized incremental — never `--full-refresh` it in a routine PR without flagging the cost in the PR description.
- New columns on `fct_rides` require either a backfill plan or an incremental-safe default.

## Required quality gates before a PR is "done"

Run these from `bikeshare/` (or `cd bikeshare && ...`):

```bash
dbt deps                                   # in case packages.yml changed
dbt parse                                  # catches Jinja and YAML errors fast
dbt build --select state:modified+ \
          --state ./target                 # build only what you changed and downstream
```

If you touched a staging or intermediate model, `state:modified+` will pull marts in automatically. If `dbt parse` or `dbt build` fails, do not open a PR — fix it first.

For ad-hoc verification of a specific model: `dbt build --select <model_name>`.

## Adding a new bikeshare system

The README has the full checklist (search for "Adding a new bikeshare system"). The short version: new staging model + sources.yml + models.yml, one new `UNION ALL` block in `int_rides__unioned.sql`, and a new filename pattern + `already_loaded` call in `scripts/load_unprocessed_csvs.sh`. The marts layer does not need to change.

## Don'ts

- Don't commit anything under `data/` or `logs/`.
- Don't put credentials in `dbt_project.yml` or any file in the repo — `~/.dbt/profiles.yml` is the only place credentials live.
- Don't create new top-level model directories (staging/intermediate/marts is the agreed layering).
- Don't add a "utils" or "helpers" macro file just for one macro — keep macros in `bikeshare/macros/` only when reused.
