"""Monitoring Agent: consume service health and publish monitoring alerts."""
from __future__ import annotations

from typing import Any, Dict, Optional

from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

from messaging.consumer import get_consumer
from messaging.healthcheck import check_kafka_connection
from messaging.producer import get_producer
from messaging.topics import TOPICS


def build_alert_from_health(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build an alert dict from a service_health record. Return None if no alert."""
    if not isinstance(record, dict):
        return None

    status = (record.get("status") or "").lower()
    if status == "healthy":
        return None
    if status not in {"degraded", "failed"}:
        return None

    service = record.get("service")
    if not service:
        return None

    severity_score = record.get("severity_score", 0) or 0
    try:
        score_val = float(severity_score)
    except (TypeError, ValueError):
        score_val = 0.0

    if score_val >= 0.8:
        severity = "critical"
    elif score_val >= 0.4:
        severity = "warning"
    else:
        severity = "info"

    return {
        "event_type": "monitoring_alert",
        "service": service,
        "snapshot_time": record.get("snapshot_time"),
        "status": status,
        "severity": severity,
        "severity_score": score_val,
        "anomaly_flags": record.get("anomaly_flags", []),
        "evidence": record.get("evidence", []),
    }


def run() -> None:
    if not check_kafka_connection():
        return

    health_topic = TOPICS["telemetry_service_health"]
    context_topic = TOPICS["snapshot_context"]
    publish_topic = TOPICS["agent_monitoring_alerts"]

    # Subscribe to both service health and snapshot context so alerts carry run_id/scenario
    consumer = get_consumer(
        health_topic,
        context_topic,
        group_id="jatayu-monitoring-agent",
        auto_offset_reset="latest",
    )
    producer = get_producer()

    print(
        f"[Monitoring] Starting agent | consume=[{health_topic}, {context_topic}] | publish={publish_topic}"
    )

    last_run_id: Optional[str] = None
    last_scenario: Optional[str] = None

    try:
        for msg in consumer:
            # Track snapshot context so alerts include run_id and scenario
            if msg.topic == context_topic:
                ctx = msg.value
                if isinstance(ctx, dict):
                    last_run_id = ctx.get("run_id") or last_run_id
                    last_scenario = ctx.get("scenario") or last_scenario
                continue

            record = msg.value
            alert = build_alert_from_health(record)
            if not alert:
                continue

            # Embed context so downstream agents (RCA, Decision, Reporting) have it
            if last_run_id:
                alert["run_id"] = last_run_id
            if last_scenario:
                alert["scenario"] = last_scenario

            key = alert.get("service")
            try:
                future = producer.send(publish_topic, value=alert, key=key)
                future.get(timeout=10)
                print(f"[Monitoring] Alert published for {key} ({alert['severity']}) run={last_run_id} scenario={last_scenario}")
            except (KafkaTimeoutError, NoBrokersAvailable) as exc:
                print(f"[ERROR] Kafka broker unavailable when publishing to {publish_topic}: {exc}")
                break
            except KafkaError as exc:
                print(f"[Monitoring][ERROR] Failed to publish alert for {key}: {exc}")
    except KeyboardInterrupt:
        print("[Monitoring] Stopping agent (keyboard interrupt)")
    finally:
        try:
            producer.flush()
        finally:
            producer.close()
            consumer.close()


if __name__ == "__main__":
    run()
