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
SLEEP_SECONDS_OVERRIDE="${PROB_GAP_SLEEP_SECONDS:-}"
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

ensure_pydeps() {
  local target="$1"
  local marker="$target/.probability_gap_pydeps_ready"
  local tmp_target="${target}.tmp.$$"
  local check_script="import aiohttp; assert hasattr(aiohttp, 'ClientTimeout'), aiohttp"
  if [[ -f "$marker" ]] && PYTHONPATH="$target" "$PYTHON_BIN" -c "$check_script" >/dev/null 2>&1; then
    return 0
  fi
  {
    printf 'PYDEPS_REBUILD_START %s path=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$target"
  } >> "$LOG_PATH"
  rm -rf "$tmp_target"
  mkdir -p "$tmp_target"
  "$PYTHON_BIN" -m pip install --quiet --upgrade --target "$tmp_target" \
    aiohttp aiohappyeyeballs aiosignal attrs frozenlist multidict propcache yarl idna typing_extensions
  PYTHONPATH="$tmp_target" "$PYTHON_BIN" -c "$check_script"
  rm -rf "$target"
  mv "$tmp_target" "$target"
  touch "$marker"
  {
    printf 'PYDEPS_REBUILD_DONE %s path=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$target"
  } >> "$LOG_PATH"
}

local_epoch() {
  date -j -f "%Y-%m-%d %H:%M:%S" "$1" "+%s"
}

date_from_ymd() {
  local input_date="$1"
  shift
  date -j -f "%Y-%m-%d" "$input_date" "$@"
}

now_local="${PROB_GAP_SCHEDULE_NOW_LOCAL:-$(date '+%Y-%m-%d %H:%M:%S')}"
now_epoch="$(local_epoch "$now_local")"
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

hour="${now_local:11:2}"
minute="${now_local:14:2}"
iterations=""
requested_iterations=""
window_end_epoch=""
window_end_local=""
window_name=""
window_sleep_seconds=""
today="${now_local:0:10}"
tomorrow="$(date_from_ymd "$today" '-v+1d' '+%Y-%m-%d')"

if (( 10#$hour < 12 )); then
  window_name="early_observable"
  requested_iterations="${PROB_GAP_EARLY_ITERATIONS:-720}"
  window_sleep_seconds="${PROB_GAP_EARLY_SLEEP_SECONDS:-60}"
  window_end_local="$today 12:00:00"
elif (( 10#$hour >= 12 && 10#$hour < 16 )); then
  window_name="trading_core"
  requested_iterations="${PROB_GAP_TRADING_CORE_ITERATIONS:-960}"
  window_sleep_seconds="${PROB_GAP_TRADING_CORE_SLEEP_SECONDS:-15}"
  window_end_local="$today 16:00:00"
elif (( 10#$hour >= 16 && 10#$hour < 22 )); then
  window_name="post_option_observable"
  requested_iterations="${PROB_GAP_POST_OPTION_ITERATIONS:-360}"
  window_sleep_seconds="${PROB_GAP_POST_OPTION_SLEEP_SECONDS:-60}"
  window_end_local="$today 22:00:00"
elif (( 10#$hour == 22 || (10#$hour == 23 && 10#$minute < 45) )); then
  window_name="near_exit_observable"
  requested_iterations="${PROB_GAP_NEAR_EXIT_ITERATIONS:-210}"
  window_sleep_seconds="${PROB_GAP_NEAR_EXIT_SLEEP_SECONDS:-30}"
  window_end_local="$today 23:45:00"
else
  if [[ "${PROB_GAP_SCHEDULE_DRY_RUN:-0}" == "1" ]]; then
    printf 'SCHEDULE_DRY_RUN_SKIP now_local=%s reason=outside_sampling_window local_time=%s:%s\n' "$now_local" "$hour" "$minute"
  else
    {
      printf 'SCHEDULE_SKIP %s reason=outside_sampling_window local_time=%s:%s\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$hour" "$minute"
    } >> "$LOG_PATH"
  fi
  exit 0
fi
window_end_epoch="$(local_epoch "$window_end_local")"
SLEEP_SECONDS="${SLEEP_SECONDS_OVERRIDE:-$window_sleep_seconds}"

remaining_seconds=$((window_end_epoch - now_epoch))
if (( remaining_seconds <= 0 )); then
  if [[ "${PROB_GAP_SCHEDULE_DRY_RUN:-0}" == "1" ]]; then
    printf 'SCHEDULE_DRY_RUN_SKIP now_local=%s reason=window_elapsed window=%s local_time=%s:%s\n' "$now_local" "$window_name" "$hour" "$minute"
  else
    {
      printf 'SCHEDULE_SKIP %s reason=window_elapsed window=%s local_time=%s:%s\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$window_name" "$hour" "$minute"
    } >> "$LOG_PATH"
  fi
  exit 0
fi

max_window_iterations=$(((remaining_seconds + SLEEP_SECONDS - 1) / SLEEP_SECONDS))
if (( requested_iterations < max_window_iterations )); then
  iterations="$requested_iterations"
else
  iterations="$max_window_iterations"
fi

if [[ "${PROB_GAP_SCHEDULE_DRY_RUN:-0}" == "1" ]]; then
  printf 'SCHEDULE_DRY_RUN now_local=%s window=%s window_end_local=%s sleep_seconds=%s iterations=%s requested_iterations=%s remaining_seconds=%s db=%s\n' \
    "$now_local" "$window_name" "$window_end_local" "$SLEEP_SECONDS" "$iterations" "$requested_iterations" "$remaining_seconds" "$DB_PATH"
  exit 0
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

ensure_pydeps "$PYDEPS_PATH"

exec caffeinate -dimsu env PYTHONPATH="${PYDEPS_PATH}:${REPO_ROOT}" \
  PROB_GAP_PYDEPS_PATH="$PYDEPS_PATH" \
  "$PYTHON_BIN" -u scripts/probability_gap_intraday_sampling.py \
    --iterations "$iterations" \
    --sleep-seconds "$SLEEP_SECONDS" \
    --db-path "$DB_PATH" \
    >> "$LOG_PATH" 2>&1
