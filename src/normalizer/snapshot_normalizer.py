from __future__ import annotations

import json
from pathlib import Path

from normalizer.builders.service_features_builder import build_service_features
from normalizer.builders.service_health_builder import build_service_health
from normalizer.models import NormalizedSnapshot, SnapshotContext
from normalizer.parsers.events_parser import parse_events
from normalizer.parsers.log_parser import parse_log_file
from normalizer.parsers.pod_metrics_parser import parse_pod_metrics
from normalizer.parsers.pod_status_parser_json import parse_pod_status_json
from normalizer.parsers.time_parser import parse_time_file


def normalize_snapshot(snapshot_dir: str, scenario: str, run_id: str) -> NormalizedSnapshot:
    snapshot_path = Path(snapshot_dir)
    snapshot_id = snapshot_path.name

    snapshot_time = parse_time_file(str(snapshot_path / "time.txt"))

    context = SnapshotContext(
        scenario=scenario,
        run_id=run_id,
        snapshot_id=snapshot_id,
        snapshot_time=snapshot_time,
    )

    pod_metrics = parse_pod_metrics(str(snapshot_path / "pod_metrics.txt"), snapshot_time)

    # Prefer pods.json, but keep pods.txt for backward compatibility when it contains JSON.
    pods_file = snapshot_path / "pods.json"
    if not pods_file.exists():
        pods_file = snapshot_path / "pods.txt"

    pod_statuses = parse_pod_status_json(str(pods_file), snapshot_time)
    k8s_events = parse_events(str(snapshot_path / "events.txt"), snapshot_time)

    log_events = []
    logs_dir = snapshot_path / "logs"
    if logs_dir.exists():
        for log_file in logs_dir.glob("*.log"):
            log_events.extend(parse_log_file(str(log_file), snapshot_time))

    service_features = build_service_features(
        snapshot_time=snapshot_time,
        pod_metrics=pod_metrics,
        pod_statuses=pod_statuses,
        k8s_events=k8s_events,
        log_events=log_events,
    )

    service_health = build_service_health(service_features)

    return NormalizedSnapshot(
        context=context,
        pod_metrics=pod_metrics,
        pod_statuses=pod_statuses,
        k8s_events=k8s_events,
        log_events=log_events,
        service_features=service_features,
        service_health=service_health,
    )


def save_normalized_snapshot(normalized: NormalizedSnapshot, output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    def dump(filename: str, data) -> None:
        with open(out / filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    dump("snapshot_context.json", normalized.context.model_dump())
    dump("pod_metrics.json", [x.model_dump() for x in normalized.pod_metrics])
    dump("pod_status.json", [x.model_dump() for x in normalized.pod_statuses])
    dump("k8s_events.json", [x.model_dump() for x in normalized.k8s_events])
    dump("log_events.json", [x.model_dump() for x in normalized.log_events])
    dump("service_features.json", [x.model_dump() for x in normalized.service_features])
    dump("service_health.json", [x.model_dump() for x in normalized.service_health])