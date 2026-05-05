#!/usr/bin/env bash
# Load one bikeshare monthly CSV into raw.<system>_trips.
#
# This script simulates an ingestion tool (Airflow task, cron job, Fivetran)
# landing raw data in the warehouse. dbt picks up from there.
#
# Usage:
#   scripts/load_raw_csv.sh <system> <path-to-monthly-csv>
#
# Examples:
#   scripts/load_raw_csv.sh capitalbikeshare data/202601-capitalbikeshare-tripdata.csv
#   scripts/load_raw_csv.sh citibike         data/JC-202601-citibike-tripdata.csv
#
# Note: this only works because Capital Bikeshare and Citi Bike share an
# identical schema (both follow GBFS). If a new source had different columns,
# it would need its own load script and its own raw landing table shape.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <system> <path-to-monthly-csv>" >&2
  exit 1
fi

SYSTEM="$1"
RAW_TABLE="raw.${SYSTEM}_trips"
CSV_PATH="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
SOURCE_FILE="$(basename "$2")"

export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
export PGPASSWORD=dbt_password

psql -h localhost -U dbt_user -d bikeshare <<SQL
CREATE TABLE IF NOT EXISTS ${RAW_TABLE} (
    ride_id            text,
    rideable_type      text,
    started_at         text,
    ended_at           text,
    start_station_name text,
    start_station_id   text,
    end_station_name   text,
    end_station_id     text,
    start_lat          text,
    start_lng          text,
    end_lat            text,
    end_lng            text,
    member_casual      text,
    _ingested_at       timestamptz NOT NULL DEFAULT now(),
    _source_file       text
);

\copy ${RAW_TABLE} (ride_id, rideable_type, started_at, ended_at, start_station_name, start_station_id, end_station_name, end_station_id, start_lat, start_lng, end_lat, end_lng, member_casual) FROM '${CSV_PATH}' WITH (FORMAT csv, HEADER true)

UPDATE ${RAW_TABLE}
   SET _source_file = '${SOURCE_FILE}'
 WHERE _source_file IS NULL;
SQL
