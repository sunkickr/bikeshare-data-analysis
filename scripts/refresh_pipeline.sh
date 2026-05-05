#!/usr/bin/env bash
# Refresh the bikeshare pipeline end-to-end.
#
# What it does, in order:
#   1. Run load_unprocessed_csvs.sh (idempotent — only ingests new files in data/)
#   2. Run dbt build (idempotent — incremental fct_rides, full-rebuild dim/agg)
#   3. Log everything to logs/refresh_<YYYYMMDD-HHMMSS>.log
#   4. Exit non-zero if any step failed (so cron can detect failures)
#
# This script is the cron target. It does NOT download files — that concern is
# delegated to whatever lands files in data/ (manual drop, an S3 sync script,
# etc). See README for the suggested separation.
#
# Usage:  scripts/refresh_pipeline.sh
set -uo pipefail   # NOTE: not using -e so we can collect partial-failure context

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs"
TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="${LOG_DIR}/refresh_${TIMESTAMP}.log"

mkdir -p "$LOG_DIR"

# tee everything from here on into the log file as well as stdout
exec > >(tee -a "$LOG_FILE") 2>&1

echo "============================================================"
echo "refresh_pipeline.sh started: $(date)"
echo "============================================================"

# Path needs to include Postgres binaries; cron's PATH is minimal by default.
export PATH="/opt/homebrew/opt/postgresql@16/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

load_status=0
dbt_status=0

# ---------- 1. Load any new CSVs ----------
echo
echo "--- step 1: load any new CSVs ---"
"${REPO_ROOT}/scripts/load_unprocessed_csvs.sh" || load_status=$?
echo "load step exit code: $load_status"

# ---------- 2. dbt build ----------
echo
echo "--- step 2: dbt build ---"
cd "${REPO_ROOT}/bikeshare"
"${REPO_ROOT}/.venv/bin/dbt" build || dbt_status=$?
echo "dbt build exit code: $dbt_status"

# ---------- 3. Summary + housekeeping ----------
echo
echo "--- summary ---"
echo "load:  $([[ $load_status -eq 0 ]] && echo OK || echo FAIL)"
echo "dbt:   $([[ $dbt_status -eq 0 ]] && echo OK || echo FAIL)"

# Keep only the last 30 logs so this directory doesn't grow unbounded.
ls -1t "${LOG_DIR}"/refresh_*.log 2>/dev/null | tail -n +31 | xargs -r rm --

# Exit non-zero if anything failed — cron uses the exit code to detect failures.
overall=$(( load_status + dbt_status ))
echo
echo "refresh_pipeline.sh finished: $(date), overall=$overall"
exit "$overall"
