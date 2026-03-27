"""Publish a telemetry snapshot directory to Kafka topics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, List, Mapping, MutableMapping

from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

from messaging.healthcheck import check_kafka_connection
from messaging.producer import get_producer
from messaging.topics import TOPICS

FILE_TOPIC_MAP: Mapping[str, str] = {
    "snapshot_context.json": TOPICS["snapshot_context"],
    "k8s_events.json": TOPICS["telemetry_k8s_events"],
    "log_events.json": TOPICS["telemetry_log_events"],
    "pod_metrics.json": TOPICS["telemetry_pod_metrics"],
    "pod_status.json": TOPICS["telemetry_pod_status"],
    "service_features.json": TOPICS["telemetry_service_features"],
    "service_health.json": TOPICS["telemetry_service_health"],
}


def load_json_records(path: Path) -> List[MutableMapping]:
    """Load records from a JSON file, handling objects and arrays."""
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Failed to parse {path.name}: {exc}")
        return []

    if isinstance(data, list):
        return [item for item in data if isinstance(item, MutableMapping)]
    if isinstance(data, MutableMapping):
        return [data]
    return []


def publish_snapshot(snapshot_dir: Path) -> dict:
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        raise FileNotFoundError(f"Snapshot directory not found: {snapshot_dir}")

    if not check_kafka_connection():
        print("[ERROR] Kafka not reachable. Aborting publish.")
        return {"sent": 0, "failed": 0, "files": {}, "error": "kafka_unreachable"}

    producer = get_producer()

    total_sent = 0
    total_failed = 0
    file_stats: dict[str, dict[str, int]] = {}

    for filename, topic in FILE_TOPIC_MAP.items():
        file_path = snapshot_dir / filename
        if not file_path.exists():
            print(f"[SKIP] {filename} (missing)")
            continue

        records = load_json_records(file_path)
        if not records:
            print(f"[SKIP] {filename} (no records)")
            continue

        sent = 0
        failed = 0
        for record in records:
            key = record.get("service") if isinstance(record, MutableMapping) else None
            try:
                future = producer.send(topic, value=record, key=key)
                future.get(timeout=10)
                sent += 1
            except (KafkaTimeoutError, NoBrokersAvailable) as exc:
                failed += 1
                print(f"[ERROR] Broker issue when sending from {filename} to {topic}: {exc}")
                break
            except KafkaError as exc:
                failed += 1
                print(f"[ERROR] Failed to send record from {filename} to {topic}: {exc}")

        producer.flush()
        total_sent += sent
        total_failed += failed
        file_stats[filename] = {"sent": sent, "failed": failed}
        print(f"[PUBLISHED] {sent} ok / {failed} failed to {topic} from {filename}")

    producer.flush()
    producer.close()
    print(f"[SUMMARY] total_sent={total_sent} total_failed={total_failed}")
    return {"sent": total_sent, "failed": total_failed, "files": file_stats}


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish a snapshot directory to Kafka")
    parser.add_argument(
        "snapshot_dir",
        type=Path,
        help="Path to snapshot directory containing JSON files",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = _parse_args(argv)
    publish_snapshot(args.snapshot_dir)


if __name__ == "__main__":
    main()
