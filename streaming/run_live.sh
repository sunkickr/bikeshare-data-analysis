#!/usr/bin/env bash
# Launch the full live stack in one command and tear it ALL down together on Ctrl-C.
#
#   1. producer.py            GBFS -> Kafka          (new snapshot every ~60s)
#   2. consumer.py            Kafka -> local Postgres (raw)
#   3. refresh_live_marts.sh  raw  -> marts          (so the map moves)
#
# The dashboard (run separately: `.venv/bin/streamlit run dashboard/Overview.py`)
# reads what these three keep fresh. Each process logs to logs/live_*.log; this
# console shows only the refresh heartbeat + lifecycle messages.
#
# Usage:  streaming/run_live.sh      (Ctrl-C stops all three)
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${REPO_ROOT}/.venv/bin/python"
LOG_DIR="${REPO_ROOT}/logs"
mkdir -p "${LOG_DIR}"

pids=()
cleaned=0
cleanup() {
    [[ "${cleaned}" == 1 ]] && return
    cleaned=1
    echo
    echo "run_live: shutting down the live stack…"
    for pid in "${pids[@]}"; do
        kill "${pid}" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    echo "run_live: all stopped."
}
trap cleanup INT TERM EXIT

echo "run_live: starting producer (GBFS -> Kafka)…"
"${PY}" "${REPO_ROOT}/streaming/producer.py" >"${LOG_DIR}/live_producer.log" 2>&1 &
pids+=($!)

echo "run_live: starting consumer (Kafka -> Postgres)…"
"${PY}" "${REPO_ROOT}/streaming/consumer.py" >"${LOG_DIR}/live_consumer.log" 2>&1 &
pids+=($!)

echo "run_live: starting mart refresh loop (raw -> marts)…"
"${REPO_ROOT}/streaming/refresh_live_marts.sh" &
pids+=($!)

echo "run_live: live stack running (3 processes). Logs in ${LOG_DIR}/live_*.log. Ctrl-C to stop all."
wait
