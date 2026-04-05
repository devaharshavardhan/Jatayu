# JATAYU — Messaging Layer & Service Registry
## Document 8 of 10: `messaging/` + `registry/` — All Python Files

---

## FILE: `messaging/config.py`

```python
"""Kafka configuration helpers for JATAYU local dev."""
from __future__ import annotations

import os


def get_bootstrap_servers() -> str:
    """Return bootstrap servers from env or default localhost:9092."""
    return os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


def get_common_client_id(prefix: str) -> str:
    return f"jatayu-{prefix}"
```

---

## FILE: `messaging/topics.py`

```python
"""Topic constants for JATAYU messaging."""

JATAYU_SNAPSHOT_CONTEXT = "jatayu.snapshot.context"
JATAYU_TELEMETRY_K8S_EVENTS = "jatayu.telemetry.k8s_events"
JATAYU_TELEMETRY_LOG_EVENTS = "jatayu.telemetry.log_events"
JATAYU_TELEMETRY_POD_METRICS = "jatayu.telemetry.pod_metrics"
JATAYU_TELEMETRY_POD_STATUS = "jatayu.telemetry.pod_status"
JATAYU_TELEMETRY_SERVICE_FEATURES = "jatayu.telemetry.service_features"
JATAYU_TELEMETRY_SERVICE_HEALTH = "jatayu.telemetry.service_health"

JATAYU_AGENT_MONITORING_ALERTS = "jatayu.agent.monitoring.alerts"
JATAYU_AGENT_PREDICTION_RISKS = "jatayu.agent.prediction.risks"
JATAYU_AGENT_RCA_RESULTS = "jatayu.agent.rca.results"
JATAYU_AGENT_DECISION_INTENTS = "jatayu.agent.decision.intents"
JATAYU_AGENT_REMEDIATION_RESULTS = "jatayu.agent.remediation.results"
JATAYU_AGENT_REPORTING_INCIDENTS = "jatayu.agent.reporting.incidents"

TOPICS = {
    "snapshot_context": JATAYU_SNAPSHOT_CONTEXT,
    "telemetry_k8s_events": JATAYU_TELEMETRY_K8S_EVENTS,
    "telemetry_log_events": JATAYU_TELEMETRY_LOG_EVENTS,
    "telemetry_pod_metrics": JATAYU_TELEMETRY_POD_METRICS,
    "telemetry_pod_status": JATAYU_TELEMETRY_POD_STATUS,
    "telemetry_service_features": JATAYU_TELEMETRY_SERVICE_FEATURES,
    "telemetry_service_health": JATAYU_TELEMETRY_SERVICE_HEALTH,
    "agent_monitoring_alerts": JATAYU_AGENT_MONITORING_ALERTS,
    "agent_prediction_risks": JATAYU_AGENT_PREDICTION_RISKS,
    "agent_rca_results": JATAYU_AGENT_RCA_RESULTS,
    "agent_decision_intents": JATAYU_AGENT_DECISION_INTENTS,
    "agent_remediation_results": JATAYU_AGENT_REMEDIATION_RESULTS,
    "agent_reporting_incidents": JATAYU_AGENT_REPORTING_INCIDENTS,
}
```

---

## FILE: `messaging/healthcheck.py`

```python
"""Kafka connectivity health check for local dev."""
from __future__ import annotations

import sys
from typing import Optional

from kafka import KafkaConsumer
from kafka.errors import KafkaError, NoBrokersAvailable, KafkaTimeoutError

from messaging.config import get_bootstrap_servers, get_common_client_id


def check_kafka_connection(timeout_seconds: int = 5) -> bool:
    bootstrap = get_bootstrap_servers()
    try:
        consumer = KafkaConsumer(
            bootstrap_servers=bootstrap,
            client_id=get_common_client_id("healthcheck"),
            request_timeout_ms=timeout_seconds * 1000,
            metadata_max_age_ms=timeout_seconds * 1000,
            consumer_timeout_ms=timeout_seconds * 1000,
        )
        consumer.topics()  # triggers metadata fetch
        consumer.close()
        print(f"[Healthcheck] Kafka reachable at {bootstrap}")
        return True
    except (NoBrokersAvailable, KafkaTimeoutError) as exc:
        print(f"[ERROR] Kafka broker unavailable at {bootstrap}: {exc}")
    except KafkaError as exc:
        print(f"[ERROR] Kafka metadata fetch failed at {bootstrap}: {exc}")
    except Exception as exc:
        print(f"[ERROR] Unexpected error checking Kafka at {bootstrap}: {exc}")
    return False


def _main(argv: Optional[list[str]] = None) -> int:
    ok = check_kafka_connection()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main())
```

---

## FILE: `messaging/producer.py`

```python
"""Reusable Kafka producer factory with centralized config."""
from __future__ import annotations

import json
from typing import Optional

from kafka import KafkaProducer

from messaging.config import get_bootstrap_servers, get_common_client_id


def _serialize_value(value) -> bytes:
    return json.dumps(value).encode("utf-8")


def _serialize_key(key: Optional[str]) -> Optional[bytes]:
    return str(key).encode("utf-8") if key is not None else None


def get_producer() -> KafkaProducer:
    """Create a KafkaProducer with sensible defaults for local dev."""
    return KafkaProducer(
        bootstrap_servers=get_bootstrap_servers(),
        client_id=get_common_client_id("producer"),
        acks="all",
        retries=3,
        linger_ms=5,
        request_timeout_ms=15000,
        max_block_ms=15000,
        metadata_max_age_ms=30000,
        value_serializer=_serialize_value,
        key_serializer=_serialize_key,
    )
```

---

## FILE: `messaging/consumer.py`

```python
"""Kafka consumer factory with centralized config."""
from __future__ import annotations

import json
from typing import Any

from kafka import KafkaConsumer

from messaging.config import get_bootstrap_servers, get_common_client_id


def get_consumer(*topics: str, group_id: str, auto_offset_reset: str = "latest") -> KafkaConsumer:
    return KafkaConsumer(
        *topics,
        bootstrap_servers=get_bootstrap_servers(),
        client_id=get_common_client_id("consumer"),
        group_id=group_id,
        auto_offset_reset=auto_offset_reset,
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
        request_timeout_ms=30000,
        session_timeout_ms=10000,
        heartbeat_interval_ms=3000,
    )
```

---

## FILE: `messaging/publisher.py`

Reads JSON files from a snapshot directory and publishes each record to the correct Kafka topic. Maps `service_health.json` → `jatayu.telemetry.service_health`, etc.

```python
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
```

---

## FILE: `registry/registry_loader.py`

```python
"""Service Registry loader - loads and exposes service metadata."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_REGISTRY_PATH = Path(__file__).parent / "service_registry.json"
_registry_cache: Optional[Dict[str, Any]] = None


def _load() -> Dict[str, Any]:
    global _registry_cache
    if _registry_cache is None:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            _registry_cache = json.load(f)
    return _registry_cache


def get_all_services() -> Dict[str, Any]:
    return _load().get("services", {})


def get_service(name: str) -> Optional[Dict[str, Any]]:
    return get_all_services().get(name)


def get_remediation_policies(service: str) -> List[str]:
    svc = get_service(service)
    return svc.get("remediation_policies", []) if svc else []


def is_safe_to_auto_remediate(service: str) -> bool:
    svc = get_service(service)
    return bool(svc.get("safe_to_auto_remediate", False)) if svc else False


def get_criticality(service: str) -> str:
    svc = get_service(service)
    return svc.get("criticality", "medium") if svc else "medium"


def get_k8s_resource(service: str) -> Optional[str]:
    svc = get_service(service)
    return svc.get("k8s_resource") if svc else None


def get_namespace(service: str) -> str:
    svc = get_service(service)
    return svc.get("namespace", "default") if svc else "default"
```

---

## Kafka Topic Map Reference

| File (in snapshot dir) | Kafka Topic |
|---|---|
| `snapshot_context.json` | `jatayu.snapshot.context` |
| `k8s_events.json` | `jatayu.telemetry.k8s_events` |
| `log_events.json` | `jatayu.telemetry.log_events` |
| `pod_metrics.json` | `jatayu.telemetry.pod_metrics` |
| `pod_status.json` | `jatayu.telemetry.pod_status` |
| `service_features.json` | `jatayu.telemetry.service_features` |
| `service_health.json` | `jatayu.telemetry.service_health` |
| *(Monitoring Agent output)* | `jatayu.agent.monitoring.alerts` |
| *(Prediction Agent output)* | `jatayu.agent.prediction.risks` |
| *(RCA Agent output)* | `jatayu.agent.rca.results` |
| *(Decision Agent output)* | `jatayu.agent.decision.intents` |
| *(Remediation Agent output)* | `jatayu.agent.remediation.results` |
| *(Reporting Agent output)* | `jatayu.agent.reporting.incidents` |

---

## Producer Configuration Notes

- `acks="all"` — waits for all in-sync replicas to acknowledge (data safety)
- `retries=3` — automatic retry on transient failures
- `linger_ms=5` — small batching window for throughput
- `max_block_ms=15000` — max time to block on `send()` if buffer is full

## Consumer Configuration Notes

- `group_id` per agent — each agent has an isolated consumer group
- `auto_offset_reset="latest"` — agents only process new messages (not replays from old offsets)
- `enable_auto_commit=True` — offsets committed automatically
- `kafka_view_service` uses `group_id=None` (no group) + seeks to `end_offset - N` for read-only inspection
