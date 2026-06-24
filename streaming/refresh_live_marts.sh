#!/usr/bin/env bash
# Loop #3 of the live stack: roll fresh raw snapshots into the marts on a cadence
# so the dashboard map actually moves.
#
#   producer.py -> consumer.py -> [THIS] -> dashboard
#   (GBFS->Kafka)  (Kafka->raw)    (raw->marts)  (reads marts)
#
# Rebuilds fct_cabi_station_status (incremental — only new snapshots) and its
# downstream agg every REFRESH_SECONDS. Ctrl-C to stop.
#
# Usage:  streaming/refresh_live_marts.sh     (REFRESH_SECONDS=60 by default)
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REFRESH_SECONDS="${REFRESH_SECONDS:-60}"
DBT="${REPO_ROOT}/.venv/bin/dbt"
LOG="${REPO_ROOT}/logs/refresh_live_marts.log"

mkdir -p "${REPO_ROOT}/logs"
# cron's/launcher's PATH is minimal; dbt-postgres shells out to nothing here, but
# keep Postgres bins on PATH for parity with refresh_pipeline.sh.
export PATH="/opt/homebrew/opt/postgresql@16/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd "${REPO_ROOT}/bikeshare"

trap 'echo "refresh_live_marts: stopping."; exit 0' INT TERM

echo "refresh_live_marts: rebuilding fct_cabi_station_status+ every ${REFRESH_SECONDS}s (full output -> ${LOG}). Ctrl-C to stop."
while true; do
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    if "${DBT}" build --select fct_cabi_station_status+ >>"${LOG}" 2>&1; then
        echo "[${ts}] live marts rebuilt OK"
    else
        echo "[${ts}] live marts rebuild FAILED — see ${LOG}" >&2
    fi
    sleep "${REFRESH_SECONDS}"
done
