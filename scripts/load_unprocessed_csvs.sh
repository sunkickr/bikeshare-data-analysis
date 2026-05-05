#!/usr/bin/env bash
# Detect every *.csv under data/ that hasn't already been loaded into raw, and
# load it via load_raw_csv.sh. Idempotent: safe to run any number of times.
#
# "Already loaded" is defined as: the basename of the file appears in the
# _source_file column of the corresponding raw.<system>_trips table.
#
# Filename → system mapping:
#   *capitalbikeshare-tripdata*.csv  → capitalbikeshare
#   *citibike-tripdata*.csv          → citibike   (handles JC- prefix and split parts)
#
# Usage:  scripts/load_unprocessed_csvs.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${REPO_ROOT}/data"

export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
export PGPASSWORD=dbt_password

# Pull the set of already-loaded file basenames per system. Use `|| true` so
# missing raw tables (first-ever run) don't crash us — they'll just yield empty.
already_loaded() {
  local system="$1"
  psql -h localhost -U dbt_user -d bikeshare -t -A \
    -c "SELECT DISTINCT _source_file FROM raw.${system}_trips" 2>/dev/null \
    | grep -v '^$' \
    | sort -u \
    || true
}

system_for_file() {
  local filename="$1"
  case "$filename" in
    *capitalbikeshare-tripdata*.csv) echo "capitalbikeshare" ;;
    *citibike-tripdata*.csv)         echo "citibike" ;;
    *)                               echo "" ;;
  esac
}

cb_loaded=$(already_loaded capitalbikeshare)
cb_loaded=$(echo "$cb_loaded")  # collapse to single string for grep
ct_loaded=$(already_loaded citibike)
ct_loaded=$(echo "$ct_loaded")

new_count=0
skip_count=0
fail_count=0

for csv_path in "${DATA_DIR}"/*.csv; do
  [[ -f "$csv_path" ]] || continue   # no CSVs at all → loop body skipped

  filename="$(basename "$csv_path")"
  system="$(system_for_file "$filename")"

  if [[ -z "$system" ]]; then
    echo "[skip] unknown system for: $filename"
    skip_count=$((skip_count + 1))
    continue
  fi

  # Decide if this file is already loaded
  case "$system" in
    capitalbikeshare) loaded_list="$cb_loaded" ;;
    citibike)         loaded_list="$ct_loaded" ;;
  esac

  if echo "$loaded_list" | grep -Fxq "$filename"; then
    echo "[skip] already loaded: $filename"
    skip_count=$((skip_count + 1))
    continue
  fi

  echo "[load] $filename → raw.${system}_trips"
  if "${REPO_ROOT}/scripts/load_raw_csv.sh" "$system" "$csv_path"; then
    new_count=$((new_count + 1))
  else
    echo "[FAIL] load failed for: $filename" >&2
    fail_count=$((fail_count + 1))
  fi
done

echo
echo "loaded: $new_count   skipped: $skip_count   failed: $fail_count"
exit $fail_count
