#!/bin/bash

set -euo pipefail

DATASET_DIR="dataset"
OUTPUT_DIR="normalized"
STATE_FILE=".processed_runs"

# Activate Python path once (cleaner)
export PYTHONPATH=src

PYTHON_CMD="python src/normalizer/run_normalizer.py"

touch "$STATE_FILE"

log() {
  echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] $1"
}

is_processed() {
  grep -Fxq "$1" "$STATE_FILE"
}

mark_processed() {
  echo "$1" >> "$STATE_FILE"
}

log "Starting auto-normalization watcher..."

while true; do

  # Loop scenarios safely
  for SCENARIO_PATH in "$DATASET_DIR"/*; do
    [ -d "$SCENARIO_PATH" ] || continue

    SCENARIO=$(basename "$SCENARIO_PATH")

    for RUN_PATH in "$SCENARIO_PATH"/*; do
      [ -d "$RUN_PATH" ] || continue

      RUN_ID=$(basename "$RUN_PATH")

      KEY="$SCENARIO/$RUN_ID"

      # Skip if already processed
      if is_processed "$KEY"; then
        continue
      fi

      # Check if at least one snapshot exists
      if compgen -G "$RUN_PATH/snapshot_*" > /dev/null; then

        log "New run detected: $KEY"

        # Normalize entire run
        $PYTHON_CMD \
          --scenario "$SCENARIO" \
          --run-id "$RUN_ID"

        mark_processed "$KEY"

        log "Normalized run: $KEY"
      fi

    done
  done

  sleep 5

done