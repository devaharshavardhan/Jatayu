#!/bin/bash

set -euo pipefail

DATASET_DIR="dataset"

SCENARIOS=(
  c_pod_kill
  c_cpu_spike
  c_network_delay
  c_redis_failure
)

SNAPSHOT_COUNT=5
SAMPLE_INTERVAL=5
STABILIZE_TIME=60

log() {
  echo "[ $(date '+%Y-%m-%d %H:%M:%S') ] $1"
}

log "Starting experiment pipeline"

for SCENARIO in "${SCENARIOS[@]}"
do
  YAML_FILE="${SCENARIO}.yaml"

  if [[ ! -f "$YAML_FILE" ]]; then
      log "ERROR: $YAML_FILE not found"
      exit 1
  fi

  log "Running scenario: $SCENARIO"
  log "Using manifest: $YAML_FILE"

  EXPERIMENT_TIME=$(date +%s)
  mkdir -p "$DATASET_DIR/$SCENARIO/$EXPERIMENT_TIME"

  log "Applying chaos manifest"
  kubectl apply -f "$YAML_FILE"
  log "Chaos injected successfully"

  log "Collecting telemetry..."

  for ((SNAPSHOT_ID=0; SNAPSHOT_ID<SNAPSHOT_COUNT; SNAPSHOT_ID++))
  do
      log "Collecting snapshot $SNAPSHOT_ID for $SCENARIO"
      bash collect_telemetry.sh "$SCENARIO" "$EXPERIMENT_TIME" "$SNAPSHOT_ID"

      if [[ $SNAPSHOT_ID -lt $((SNAPSHOT_COUNT-1)) ]]; then
          sleep "$SAMPLE_INTERVAL"
      fi
  done

  log "Removing chaos experiment for $SCENARIO"
  kubectl delete -f "$YAML_FILE" --ignore-not-found --wait=false || true
  log "Delete request sent for $SCENARIO"

  log "Cluster stabilization for $SCENARIO"
  sleep "$STABILIZE_TIME"

  log "Scenario completed: $SCENARIO"
  echo "------------------------------------"
done

log "All experiments completed"