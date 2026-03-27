"""Prediction Agent: consume service features and emit prediction risks."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

from messaging.consumer import get_consumer
from messaging.healthcheck import check_kafka_connection
from messaging.producer import get_producer
from messaging.topics import TOPICS


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def derive_run_context(
    record: Dict[str, Any], latest_context: Optional[Dict[str, Any]]
) -> Tuple[str, str]:
    run_id = record.get("run_id")
    scenario = record.get("scenario")

    if run_id and scenario:
        return str(run_id), str(scenario)

    if latest_context:
        ctx_time = latest_context.get("snapshot_time")
        rec_time = record.get("snapshot_time")
        if not rec_time or rec_time == ctx_time:
            return (
                str(latest_context.get("run_id", "unknown_run")),
                str(latest_context.get("scenario", "unknown_scenario")),
            )

    return "unknown_run", "unknown_scenario"


def compute_optional_model_score(current: Dict[str, Any], history: List[Dict[str, Any]]) -> float:
    """Placeholder for future ML (Isolation Forest / PyOD / Kats / Merlion)."""
    return 0.0


def compute_risk(
    current: Dict[str, Any], previous: Dict[str, Any], recent_history: List[Dict[str, Any]]
) -> Tuple[float, str, List[str]]:
    risk_score = 0.0
    rationale: List[str] = []
    predicted_failure_type: Optional[str] = None

    prev_cpu = safe_float(previous.get("cpu_millicores"))
    cur_cpu = safe_float(current.get("cpu_millicores"))
    if prev_cpu > 0 and cur_cpu > prev_cpu * 1.25:
        risk_score += 0.35
        rationale.append(f"CPU rising from {prev_cpu} to {cur_cpu} millicores")
        predicted_failure_type = predicted_failure_type or "cpu_saturation"
    if cur_cpu >= 800:
        risk_score += 0.20
        rationale.append(f"CPU already high at {cur_cpu} millicores")
        predicted_failure_type = predicted_failure_type or "cpu_saturation"

    prev_restarts = safe_int(previous.get("restart_count"))
    cur_restarts = safe_int(current.get("restart_count"))
    if cur_restarts > prev_restarts:
        risk_score += 0.25
        rationale.append(f"Restart count increased from {prev_restarts} to {cur_restarts}")
        predicted_failure_type = predicted_failure_type or "pod_instability"
    if cur_restarts >= 5:
        risk_score += 0.15
        rationale.append(f"Restart count already elevated at {cur_restarts}")

    prev_warn = safe_int(previous.get("warning_event_count"))
    cur_warn = safe_int(current.get("warning_event_count"))
    if cur_warn > prev_warn:
        risk_score += 0.15
        rationale.append(f"Warning events increased from {prev_warn} to {cur_warn}")

    prev_unhealthy = safe_int(previous.get("unhealthy_event_count"))
    cur_unhealthy = safe_int(current.get("unhealthy_event_count"))
    if cur_unhealthy > prev_unhealthy:
        risk_score += 0.20
        rationale.append(
            f"Unhealthy events increased from {prev_unhealthy} to {cur_unhealthy}"
        )

    cur_failed_create = safe_int(current.get("failed_create_count"))
    if cur_failed_create > 0:
        risk_score += 0.30
        rationale.append("Failed create events observed")
        predicted_failure_type = predicted_failure_type or "deployment_failure"

    prev_log_err = safe_int(previous.get("log_error_count"))
    cur_log_err = safe_int(current.get("log_error_count"))
    if cur_log_err > prev_log_err:
        risk_score += 0.20
        rationale.append(f"Log errors increased from {prev_log_err} to {cur_log_err}")
        predicted_failure_type = predicted_failure_type or "service_degradation"

    prev_http_err = safe_int(previous.get("http_error_count"))
    cur_http_err = safe_int(current.get("http_error_count"))
    if cur_http_err > prev_http_err:
        risk_score += 0.20
        rationale.append(f"HTTP errors increased from {prev_http_err} to {cur_http_err}")
        predicted_failure_type = predicted_failure_type or "service_degradation"

    prev_latency = previous.get("avg_latency_ms")
    cur_latency = current.get("avg_latency_ms")
    if prev_latency is not None and cur_latency is not None:
        try:
            prev_lat = float(prev_latency)
            cur_lat = float(cur_latency)
            if prev_lat > 0 and cur_lat > prev_lat * 1.30:
                risk_score += 0.20
                rationale.append(
                    f"Latency increased from {prev_lat} ms to {cur_lat} ms"
                )
                predicted_failure_type = predicted_failure_type or "latency_degradation"
        except (TypeError, ValueError):
            pass

    anomaly_flags = current.get("anomaly_flags") or []
    if isinstance(anomaly_flags, list):
        if "high_restarts" in anomaly_flags:
            risk_score += 0.10
        if "readiness_probe_failed" in anomaly_flags:
            risk_score += 0.15
        if "pod_killed" in anomaly_flags:
            risk_score += 0.10
        if "cpu_high" in anomaly_flags:
            risk_score += 0.10

    # Persistent anomalies across last 3 records
    if len(recent_history) >= 3:
        last_three = list(recent_history)[-3:]
        if all((r.get("anomaly_flags") for r in last_three)):
            risk_score += 0.15
            rationale.append("Persistent anomalies across recent snapshots")

    pod_status = (current.get("pod_status") or "").lower()
    if pod_status and pod_status != "running":
        risk_score += 0.25
        rationale.append(f"Pod status is {pod_status}")
        predicted_failure_type = predicted_failure_type or "pod_unhealthy"

    # Optional model hook
    risk_score += compute_optional_model_score(current, list(recent_history))

    risk_score = min(risk_score, 0.99)
    risk_score = round(risk_score, 2)

    if not predicted_failure_type:
        predicted_failure_type = "generic_service_risk"

    return risk_score, predicted_failure_type, rationale


def build_prediction_event(
    service: str,
    run_id: str,
    scenario: str,
    snapshot_time: Any,
    risk_score: float,
    predicted_failure_type: str,
    rationale: List[str],
    current: Dict[str, Any],
) -> Dict[str, Any]:
    if risk_score >= 0.80:
        risk_level = "critical"
    elif risk_score >= 0.60:
        risk_level = "high"
    else:
        risk_level = "medium"

    return {
        "event_type": "prediction_risk",
        "agent": "prediction_agent",
        "service": service,
        "run_id": run_id,
        "scenario": scenario,
        "snapshot_time": snapshot_time,
        "prediction_window": "next_snapshot",
        "risk_score": risk_score,
        "risk_level": risk_level,
        "predicted_failure_type": predicted_failure_type,
        "rationale": rationale,
        "current_flags": current.get("anomaly_flags", []),
        "evidence": current.get("evidence", []),
    }


def run() -> None:
    if not check_kafka_connection():
        return

    features_topic = TOPICS["telemetry_service_features"]
    context_topic = TOPICS.get("telemetry_snapshot_context") or TOPICS.get("snapshot_context")
    topics_to_subscribe = [features_topic]
    if context_topic:
        topics_to_subscribe.append(context_topic)

    consumer = get_consumer(
        *topics_to_subscribe,
        group_id="jatayu-prediction-agent",
        auto_offset_reset="latest",
    )
    producer = get_producer()

    print(
        f"[Prediction] Starting agent | consume={topics_to_subscribe} | publish={TOPICS['agent_prediction_risks']}"
    )

    history: Dict[Tuple[str, str], Deque[Dict[str, Any]]] = defaultdict(
        lambda: deque(maxlen=5)
    )
    latest_snapshot_context: Optional[Dict[str, Any]] = None

    try:
        for msg in consumer:
            if msg.topic == context_topic:
                latest_snapshot_context = msg.value if isinstance(msg.value, dict) else None
                continue

            if msg.topic != features_topic:
                continue

            record = msg.value
            if not isinstance(record, dict):
                continue

            service = record.get("service")
            if not service:
                continue

            run_id, scenario = derive_run_context(record, latest_snapshot_context)
            key = (run_id, service)

            history[key].append(record)
            recent = history[key]
            if len(recent) < 2:
                continue

            current = recent[-1]
            previous = recent[-2]

            risk_score, predicted_failure_type, rationale = compute_risk(
                current, previous, list(recent)
            )

            if risk_score < 0.40:
                continue

            event = build_prediction_event(
                service=service,
                run_id=run_id,
                scenario=scenario,
                snapshot_time=current.get("snapshot_time"),
                risk_score=risk_score,
                predicted_failure_type=predicted_failure_type,
                rationale=rationale,
                current=current,
            )

            try:
                future = producer.send(
                    TOPICS["agent_prediction_risks"], value=event, key=service
                )
                future.get(timeout=10)
                print(f"[Prediction] Risk published for {service} ({risk_score})")
            except (KafkaTimeoutError, NoBrokersAvailable) as exc:
                print(f"[ERROR] Kafka broker unavailable when publishing to {TOPICS['agent_prediction_risks']}: {exc}")
                break
            except KafkaError as exc:
                print(f"[Prediction][ERROR] Failed to publish risk for {service}: {exc}")
    except KeyboardInterrupt:
        print("[Prediction] Stopping agent (keyboard interrupt)")
    finally:
        try:
            producer.flush()
        finally:
            producer.close()
            consumer.close()


if __name__ == "__main__":
    run()
