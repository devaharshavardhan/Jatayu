#!/bin/bash

set -euo pipefail

NAMESPACE="default"
CHAOS_NAMESPACE="chaos-testing"

DATASET_DIR="dataset"

SCENARIOS=(
c_pod_kill
c_cpu_spike
c_network_delay
c_redis_failure
)

CHAOS_DURATION=40
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

  EXPERIMENT_TIME=$(date +%s)
  EXP_DIR="$DATASET_DIR/$SCENARIO/$EXPERIMENT_TIME"

  mkdir -p "$EXP_DIR"

  kubectl apply -f "$YAML_FILE"

  log "Chaos injected. Collecting telemetry..."

  END_TIME=$((SECONDS + CHAOS_DURATION))
  SNAPSHOT_ID=0

  while [ $SECONDS -lt $END_TIME ]
  do
      bash collect_telemetry.sh "$SCENARIO" "$EXPERIMENT_TIME" "$SNAPSHOT_ID"
      SNAPSHOT_ID=$((SNAPSHOT_ID+1))
      sleep $SAMPLE_INTERVAL
  done

  log "Removing chaos experiment"
  kubectl delete -f "$YAML_FILE" --ignore-not-found

  log "Cluster stabilization"
  sleep $STABILIZE_TIME

  log "Scenario completed: $SCENARIO"
  echo "------------------------------------"

done

log "All experiments completed"