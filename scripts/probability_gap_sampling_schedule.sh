#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DB_PATH="${PROB_GAP_DB_PATH:-.yxg/data/probability_gap_samples_wu006_clean.sqlite}"
LOG_PATH="${PROB_GAP_LOG_PATH:-/tmp/probability_gap_sampling_wu006_clean.log}"
STATE_DIR="${PROB_GAP_STATE_DIR:-.yxg/data}"
DB_BASENAME="$(basename "$DB_PATH" .sqlite)"
START_FILE="$STATE_DIR/probability_gap_sampling_schedule_${DB_BASENAME}_started_at"
RUN_DAYS="${PROB_GAP_RUN_DAYS:-10}"
SLEEP_SECONDS="${PROB_GAP_SLEEP_SECONDS:-15}"
PYDEPS_PATH="${PROB_GAP_PYDEPS_PATH:-/tmp/hb_pydeps}"
DEFAULT_PYTHON_BIN="/Users/bytedance/.pyenv/versions/3.12.4/bin/python"
if [[ -n "${PROB_GAP_PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PROB_GAP_PYTHON_BIN"
elif [[ -x "$DEFAULT_PYTHON_BIN" ]]; then
  PYTHON_BIN="$DEFAULT_PYTHON_BIN"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  PYTHON_BIN="$(command -v python)"
fi

mkdir -p "$STATE_DIR" "$(dirname "$LOG_PATH")"

local_epoch() {
  date -j -f "%Y-%m-%d %H:%M:%S" "$1" "+%s"
}

now_epoch="$(date +%s)"
if [[ ! -f "$START_FILE" ]]; then
  printf '%s\n' "$now_epoch" > "$START_FILE"
fi

started_epoch="$(cat "$START_FILE")"
end_epoch=$((started_epoch + RUN_DAYS * 24 * 60 * 60))
if (( now_epoch >= end_epoch )); then
  {
    printf 'SCHEDULE_STOP %s reason=run_days_elapsed started_at=%s run_days=%s\n' \
      "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$started_epoch" "$RUN_DAYS"
  } >> "$LOG_PATH"
  exit 0
fi

hour="$(date '+%H')"
minute="$(date '+%M')"
iterations=""
requested_iterations=""
window_end_epoch=""
window_name=""
today="$(date '+%Y-%m-%d')"
tomorrow="$(date -v+1d '+%Y-%m-%d')"

if (( 10#$hour >= 12 && 10#$hour < 17 )); then
  window_name="main"
  requested_iterations="${PROB_GAP_MAIN_ITERATIONS:-1080}"
  window_end_epoch="$(local_epoch "$today 17:00:00")"
elif (( 10#$hour == 22 || 10#$hour == 23 || 10#$hour == 0 )); then
  window_name="evening"
  requested_iterations="${PROB_GAP_EVENING_ITERATIONS:-400}"
  if (( 10#$hour == 0 )); then
    window_end_epoch="$(local_epoch "$today 01:00:00")"
  else
    window_end_epoch="$(local_epoch "$tomorrow 01:00:00")"
  fi
else
  {
    printf 'SCHEDULE_SKIP %s reason=outside_sampling_window local_time=%s:%s\n' \
      "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$hour" "$minute"
  } >> "$LOG_PATH"
  exit 0
fi

remaining_seconds=$((window_end_epoch - now_epoch))
if (( remaining_seconds <= 0 )); then
  {
    printf 'SCHEDULE_SKIP %s reason=window_elapsed window=%s local_time=%s:%s\n' \
      "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$window_name" "$hour" "$minute"
  } >> "$LOG_PATH"
  exit 0
fi

max_window_iterations=$(((remaining_seconds + SLEEP_SECONDS - 1) / SLEEP_SECONDS))
if (( requested_iterations < max_window_iterations )); then
  iterations="$requested_iterations"
else
  iterations="$max_window_iterations"
fi

if pgrep -f "probability_gap_intraday_sampling.py.*${DB_PATH}" >/dev/null 2>&1; then
  {
    printf 'SCHEDULE_SKIP %s reason=already_running window=%s db=%s\n' \
      "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$window_name" "$DB_PATH"
  } >> "$LOG_PATH"
  exit 0
fi

{
  printf 'SCHEDULE_START %s window=%s iterations=%s requested_iterations=%s sleep_seconds=%s remaining_seconds=%s db=%s\n' \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$window_name" "$iterations" "$requested_iterations" "$SLEEP_SECONDS" "$remaining_seconds" "$DB_PATH"
  printf 'SCHEDULE_ENV python_bin=%s pydeps=%s repo=%s\n' "$PYTHON_BIN" "$PYDEPS_PATH" "$REPO_ROOT"
} >> "$LOG_PATH"

exec caffeinate -dimsu env PYTHONPATH="${PYDEPS_PATH}:${REPO_ROOT}" \
  "$PYTHON_BIN" -u scripts/probability_gap_intraday_sampling.py \
    --iterations "$iterations" \
    --sleep-seconds "$SLEEP_SECONDS" \
    --db-path "$DB_PATH" \
    >> "$LOG_PATH" 2>&1
