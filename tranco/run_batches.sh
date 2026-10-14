#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_FILE="${1:-$ROOT_DIR/tranco/top100K-new.txt}"
BATCH_DIR="$ROOT_DIR/tranco/batches"
OUTPUT_ROOT="$ROOT_DIR/CrawlerOutputs"
BATCH_SIZE="${BATCH_SIZE:-10000}"

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"
CRAWLER_SCRIPT="${CRAWLER_SCRIPT:-$ROOT_DIR/scripts/PII_Hybrid_Crawler_Parallel.py}"

# --- Timing ---
POLL_INTERVAL=10   # seconds between resource checks
MAX_WAIT=600       # give up waiting after this many seconds and proceed anyway

# How close to baseline we need to get before proceeding (0-100, higher = stricter).
# 80 means "recover to at least 80% of the baseline free memory / CPU idle".
RECOVERY_PCT=80

# -----------------------------------------------

mkdir -p "$BATCH_DIR" "$OUTPUT_ROOT"

# Logging helper
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Read current free-memory % and CPU-idle % for this machine (Linux + macOS).
get_resources() {
  # --- Free memory % ---
  if [[ "$(uname)" == "Darwin" ]]; then
    local page_size free_pages total_pages
    page_size=$(pagesize)
    free_pages=$(vm_stat | awk '/Pages free/ {gsub(/\./,"",$3); print $3}')
    total_pages=$(( $(sysctl -n hw.memsize) / page_size ))
    MEM_FREE_PCT=$(( free_pages * 100 / total_pages ))
  else
    local mem_total mem_available
    mem_total=$(awk '/MemTotal/    {print $2}' /proc/meminfo)
    mem_available=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
    MEM_FREE_PCT=$(( mem_available * 100 / mem_total ))
  fi

  # --- CPU idle % (two-sample average for accuracy) ---
  local raw
  if [[ "$(uname)" == "Darwin" ]]; then
    raw=$(top -l2 -n0 | awk '/CPU usage/ {gsub(/%/,"",$NF); idle=$NF} END {print idle}')
  else
    raw=$(top -bn2 -d1 | grep "Cpu(s)" | tail -1 | awk '{
      for(i=1;i<=NF;i++) if($i~/id/) { gsub(/[^0-9.]/,"",$i); print int($i); exit }
    }')
  fi
  CPU_IDLE_PCT="${raw:-100}"   # fallback: assume idle if parsing fails
}

# Snapshot resources before any batch runs — this is the machine's "resting state".
snapshot_baseline() {
  log "Snapshotting baseline resources (idle machine state)..."
  get_resources
  BASELINE_MEM=$MEM_FREE_PCT
  BASELINE_CPU=$CPU_IDLE_PCT
  log "  Baseline: ${BASELINE_MEM}% mem free, ${BASELINE_CPU}% CPU idle"

  # Derived thresholds: must recover to RECOVERY_PCT% of baseline
  MEM_THRESHOLD=$(( BASELINE_MEM * RECOVERY_PCT / 100 ))
  CPU_THRESHOLD=$(( BASELINE_CPU * RECOVERY_PCT / 100 ))
  log "  Recovery targets: mem >= ${MEM_THRESHOLD}%, CPU idle >= ${CPU_THRESHOLD}%"
}

# Wait until memory AND CPU return close to their pre-run baseline.
wait_for_resources() {
  local waited=0
  log "Waiting for resources to recover to ~${RECOVERY_PCT}% of baseline..."

  while true; do
    get_resources
    log "  Now: ${MEM_FREE_PCT}% mem free, ${CPU_IDLE_PCT}% CPU idle | targets: mem>=${MEM_THRESHOLD}%, CPU>=${CPU_THRESHOLD}% (waited ${waited}s)"

    if (( MEM_FREE_PCT >= MEM_THRESHOLD && CPU_IDLE_PCT >= CPU_THRESHOLD )); then
      log "Resources recovered. Starting next batch."
      return 0
    fi

    if (( waited >= MAX_WAIT )); then
      log "WARNING: MAX_WAIT (${MAX_WAIT}s) reached. Proceeding anyway."
      return 0
    fi

    sleep "$POLL_INTERVAL"
    waited=$(( waited + POLL_INTERVAL ))
  done
}

# Run a single batch, retrying once on failure.
run_batch() {
  local batch_file="$1"
  local batch_name
  batch_name="$(basename "$batch_file")"

  log "Running crawler on $batch_name (attempt 1/2)"
  if "$PYTHON_BIN" "$CRAWLER_SCRIPT" -f "$batch_file"; then
    log "$batch_name completed successfully."
    return 0
  fi

  log "WARNING: $batch_name failed on first attempt. Retrying after a short wait..."
  sleep 30
  wait_for_resources

  log "Running crawler on $batch_name (attempt 2/2)"
  if "$PYTHON_BIN" "$CRAWLER_SCRIPT" -f "$batch_file"; then
    log "$batch_name completed successfully on retry."
    return 0
  fi

  log "ERROR: $batch_name failed on both attempts. Logging and continuing."
  echo "$batch_file" >> "$OUTPUT_ROOT/failed_batches.log"
  return 0  # don't exit the whole script; keep going
}

# -----------------------------------------------

snapshot_baseline

rm -f "$BATCH_DIR"/batch_*.txt

"$PYTHON_BIN" "$ROOT_DIR/tranco/get_batches.py" \
  --input "$INPUT_FILE" \
  --batch-size "$BATCH_SIZE" \
  --output-dir "$BATCH_DIR"

shopt -s nullglob
all_batches=( "$BATCH_DIR"/batch_*.txt )

# Skip the first N batches (set to 0 to run all batches)
SKIP_BATCHES=0
batch_files=( "${all_batches[@]:$SKIP_BATCHES}" )

if [[ ${#batch_files[@]} -eq 0 ]]; then
  log "No batches to run after skipping the first ${SKIP_BATCHES}. Exiting."
  exit 0
fi

total="${#batch_files[@]}"
log "Skipping first ${SKIP_BATCHES} batches. Running remaining ${total} batches."
current=0

for batch_file in "${batch_files[@]}"; do
  current=$(( current + 1 ))
  log "--- Batch $current / $total ($(basename "$batch_file")) ---"

  # Wait for resources before every batch except the first of this run
  if (( current > 1 )); then
    wait_for_resources
  fi

  run_batch "$batch_file"
done

log "Done. Results are in $OUTPUT_ROOT"

if [[ -f "$OUTPUT_ROOT/failed_batches.log" ]]; then
  log "WARNING: Some batches failed. See $OUTPUT_ROOT/failed_batches.log"
fi
