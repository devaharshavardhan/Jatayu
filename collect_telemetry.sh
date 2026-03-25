#!/bin/bash

SCENARIO=$1
RUN_ID=$2
SNAPSHOT=$3

NAMESPACE="default"

DIR="dataset/$SCENARIO/$RUN_ID/snapshot_$SNAPSHOT"

mkdir -p "$DIR/logs"

echo "Collecting snapshot $SNAPSHOT"

date > "$DIR/time.txt"

# Pod metrics
kubectl top pods -n $NAMESPACE > "$DIR/pod_metrics.txt" || true

# Pod status
kubectl get pods -n $NAMESPACE -o json > "$DIR/pods.json"

# Events
kubectl get events -n $NAMESPACE \
--sort-by=.metadata.creationTimestamp > "$DIR/events.txt"

# Important service logs only
SERVICES=("frontend" "checkoutservice" "cartservice" "redis-cart")

for SERVICE in "${SERVICES[@]}"
do
    kubectl logs -l app=$SERVICE -n $NAMESPACE --tail=100 \
    > "$DIR/logs/${SERVICE}.log" 2>&1 || true
done