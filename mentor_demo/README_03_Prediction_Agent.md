# JATAYU — Agent 2: Prediction Agent
## File: `agents/prediction_agent.py`

---

## Purpose

The Prediction Agent is the **second stage** in the JATAYU pipeline. It:
1. Consumes service feature vectors from `jatayu.telemetry.service_features`
2. Uses a **multi-model approach** to compute failure risk scores:
   - Heuristic scoring (always available, rule-based)
   - **Isolation Forest** anomaly detection (when scikit-learn is installed)
   - ARIMA-style trend analysis (simple linear regression)
3. Publishes `prediction_risk` events to `jatayu.agent.prediction.risks` when risk ≥ 0.35

---

## Key Design Decisions

- **Multi-model fusion**: Heuristic score (primary) + Isolation Forest (additive bonus up to +0.25) + trend analysis
- **Graceful degradation**: If scikit-learn is not installed, falls back to heuristic-only scoring
- **Per-service rolling history**: `deque(maxlen=8)` per `(run_id, service)` key for trend analysis
- **Risk threshold**: Only publishes if `risk_score >= 0.35` to filter noise
- **Time-to-failure estimation**: Maps risk score + trend → human-readable ETA

---

## Data Flow

```
jatayu.telemetry.service_features  ──▶  compute_risk()
                                           │
                               ┌───────────┼──────────────┐
                               ▼           ▼              ▼
                         Heuristic   IsolationForest  Trend Analysis
                               └───────────┼──────────────┘
                                           ▼
                                  risk_score (0.0 - 0.99)
                                           │
                                  if score >= 0.35:
                                           ▼
                              jatayu.agent.prediction.risks
```

---

## Isolation Forest Explained

Isolation Forest is an unsupervised anomaly detection algorithm. It isolates observations by randomly selecting a feature and splitting at a random value. Anomalies require fewer splits to isolate (shorter path length = higher anomaly score).

In JATAYU, the feature vector for each service is:
```
[cpu_millicores, memory_mib, restart_count, warning_events,
 unhealthy_events, failed_create_count, log_errors,
 http_errors, avg_latency_ms, anomaly_flag_count]
```

---

## Full Source Code

```python
"""Prediction Agent: consume service features and emit prediction risks.

Uses multi-model approach:
- Heuristic scoring (primary, always available)
- Isolation Forest anomaly detection (when scikit-learn is available)
- ARIMA-style trend analysis (simple linear regression on time series)
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

from messaging.consumer import get_consumer
from messaging.healthcheck import check_kafka_connection
from messaging.producer import get_producer
from messaging.topics import TOPICS

# Optional ML imports
try:
    import numpy as np
    from sklearn.ensemble import IsolationForest, RandomForestClassifier
    SKLEARN_AVAILABLE = True
    print("[Prediction] scikit-learn available — ML models enabled")
except ImportError:
    SKLEARN_AVAILABLE = False
    print("[Prediction] scikit-learn not available — using heuristic scoring only")


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


def _extract_feature_vector(record: Dict[str, Any]) -> List[float]:
    """Extract numeric feature vector for ML models."""
    return [
        safe_float(record.get("cpu_millicores")),
        safe_float(record.get("memory_mib")),
        safe_int(record.get("restart_count")),
        safe_int(record.get("warning_event_count")),
        safe_int(record.get("unhealthy_event_count")),
        safe_int(record.get("failed_create_count")),
        safe_int(record.get("log_error_count")),
        safe_int(record.get("http_error_count")),
        safe_float(record.get("avg_latency_ms") or 0),
        float(len(record.get("anomaly_flags", []) or [])),
    ]


def _isolation_forest_score(history: List[Dict[str, Any]]) -> float:
    """
    Run Isolation Forest on the feature history.
    Returns anomaly score in [0, 1] (higher = more anomalous).
    """
    if not SKLEARN_AVAILABLE or len(history) < 3:
        return 0.0
    try:
        import numpy as np
        X = np.array([_extract_feature_vector(r) for r in history])
        # contamination = fraction we expect to be anomalous
        contamination = min(0.3, 1.0 / len(X))
        clf = IsolationForest(n_estimators=50, contamination=contamination, random_state=42)
        clf.fit(X)
        scores = clf.score_samples(X)
        # Most recent record anomaly score: lower score = more anomalous
        latest_score = scores[-1]
        # Normalize to [0, 1]: -0.5 → 1.0, +0.5 → 0.0
        normalized = max(0.0, min(1.0, (-latest_score - 0.1) * 1.2))
        return round(normalized, 3)
    except Exception as exc:
        print(f"[Prediction][IsolationForest] Error: {exc}")
        return 0.0


def _trend_analysis(history: List[Dict[str, Any]], field: str) -> Tuple[str, float]:
    """
    Simple linear trend analysis on a field over recent history.
    Returns (trend_direction, rate_of_change).
    trend_direction: 'rising', 'falling', 'stable'
    """
    if len(history) < 2:
        return "stable", 0.0
    try:
        values = [safe_float(r.get(field)) for r in history]
        if all(v == 0 for v in values):
            return "stable", 0.0
        # Simple linear regression using first-differences
        diffs = [values[i+1] - values[i] for i in range(len(values)-1)]
        avg_diff = sum(diffs) / len(diffs)
        baseline = max(values[0], 1.0)
        rate = avg_diff / baseline
        if rate > 0.1:
            return "rising", round(rate, 3)
        elif rate < -0.1:
            return "falling", round(rate, 3)
        return "stable", round(rate, 3)
    except Exception:
        return "stable", 0.0


def _estimate_time_to_failure(risk_score: float, trend: str, history: List[Dict[str, Any]]) -> str:
    """Estimate time to failure based on risk score and trend."""
    if risk_score >= 0.90:
        return "imminent (<5 min)"
    if risk_score >= 0.75:
        if trend == "rising":
            return "5-15 minutes"
        return "15-30 minutes"
    if risk_score >= 0.60:
        if trend == "rising":
            return "15-30 minutes"
        return "30-60 minutes"
    if risk_score >= 0.40:
        return "1-3 hours"
    return "no failure predicted"


def compute_risk(
    current: Dict[str, Any], previous: Dict[str, Any], recent_history: List[Dict[str, Any]]
) -> Tuple[float, str, List[str], str, str]:
    """
    Compute failure risk. Returns (risk_score, failure_type, rationale, trend, time_to_failure).
    """
    risk_score = 0.0
    rationale: List[str] = []
    predicted_failure_type: Optional[str] = None

    # CPU analysis
    prev_cpu = safe_float(previous.get("cpu_millicores"))
    cur_cpu = safe_float(current.get("cpu_millicores"))
    if prev_cpu > 0 and cur_cpu > prev_cpu * 1.25:
        risk_score += 0.35
        rationale.append(f"CPU rising from {prev_cpu:.0f} to {cur_cpu:.0f} millicores (+{((cur_cpu/prev_cpu-1)*100):.0f}%)")
        predicted_failure_type = predicted_failure_type or "cpu_saturation"
    if cur_cpu >= 800:
        risk_score += 0.20
        rationale.append(f"CPU critically high at {cur_cpu:.0f} millicores")
        predicted_failure_type = predicted_failure_type or "cpu_saturation"

    # Restart analysis
    prev_restarts = safe_int(previous.get("restart_count"))
    cur_restarts = safe_int(current.get("restart_count"))
    if cur_restarts > prev_restarts:
        risk_score += 0.25
        rationale.append(f"Restart count increased from {prev_restarts} to {cur_restarts}")
        predicted_failure_type = predicted_failure_type or "pod_instability"
    if cur_restarts >= 5:
        risk_score += 0.15
        rationale.append(f"Elevated restart count: {cur_restarts}")

    # Event analysis
    prev_warn = safe_int(previous.get("warning_event_count"))
    cur_warn = safe_int(current.get("warning_event_count"))
    if cur_warn > prev_warn:
        risk_score += 0.15
        rationale.append(f"Warning events up from {prev_warn} to {cur_warn}")

    prev_unhealthy = safe_int(previous.get("unhealthy_event_count"))
    cur_unhealthy = safe_int(current.get("unhealthy_event_count"))
    if cur_unhealthy > prev_unhealthy:
        risk_score += 0.20
        rationale.append(f"Unhealthy events up from {prev_unhealthy} to {cur_unhealthy}")

    cur_failed_create = safe_int(current.get("failed_create_count"))
    if cur_failed_create > 0:
        risk_score += 0.30
        rationale.append("Failed pod create events detected")
        predicted_failure_type = predicted_failure_type or "deployment_failure"

    # Log error analysis
    prev_log_err = safe_int(previous.get("log_error_count"))
    cur_log_err = safe_int(current.get("log_error_count"))
    if cur_log_err > prev_log_err:
        risk_score += 0.20
        rationale.append(f"Log errors up from {prev_log_err} to {cur_log_err}")
        predicted_failure_type = predicted_failure_type or "service_degradation"

    # HTTP error analysis
    prev_http_err = safe_int(previous.get("http_error_count"))
    cur_http_err = safe_int(current.get("http_error_count"))
    if cur_http_err > prev_http_err:
        risk_score += 0.20
        rationale.append(f"HTTP errors up from {prev_http_err} to {cur_http_err}")
        predicted_failure_type = predicted_failure_type or "service_degradation"

    # Latency analysis
    prev_latency = previous.get("avg_latency_ms")
    cur_latency = current.get("avg_latency_ms")
    if prev_latency is not None and cur_latency is not None:
        try:
            prev_lat = float(prev_latency)
            cur_lat = float(cur_latency)
            if prev_lat > 0 and cur_lat > prev_lat * 1.30:
                risk_score += 0.20
                rationale.append(f"Latency up from {prev_lat:.0f}ms to {cur_lat:.0f}ms")
                predicted_failure_type = predicted_failure_type or "latency_degradation"
        except (TypeError, ValueError):
            pass

    # Anomaly flags
    anomaly_flags = current.get("anomaly_flags") or []
    if isinstance(anomaly_flags, list):
        if "high_restarts" in anomaly_flags:
            risk_score += 0.10
        if "readiness_probe_failed" in anomaly_flags:
            risk_score += 0.15
        if "pod_killed" in anomaly_flags:
            risk_score += 0.10
            predicted_failure_type = predicted_failure_type or "pod_kill"
        if "cpu_high" in anomaly_flags:
            risk_score += 0.10

    # Persistent anomalies across last 3 records
    if len(recent_history) >= 3:
        last_three = list(recent_history)[-3:]
        if all(r.get("anomaly_flags") for r in last_three):
            risk_score += 0.15
            rationale.append("Persistent anomalies across 3 consecutive snapshots")

    # Pod status
    pod_status = (current.get("pod_status") or "").lower()
    if pod_status and pod_status != "running":
        risk_score += 0.25
        rationale.append(f"Pod in non-running state: {pod_status}")
        predicted_failure_type = predicted_failure_type or "pod_unhealthy"

    # Isolation Forest anomaly detection (additive)
    if SKLEARN_AVAILABLE and len(recent_history) >= 3:
        iso_score = _isolation_forest_score(list(recent_history))
        if iso_score > 0.3:
            weighted = iso_score * 0.25
            risk_score += weighted
            rationale.append(f"Isolation Forest anomaly score: {iso_score:.2f} (+{weighted:.2f} risk)")

    risk_score = min(risk_score, 0.99)
    risk_score = round(risk_score, 2)

    if not predicted_failure_type:
        predicted_failure_type = "generic_service_risk"

    # Trend analysis on CPU
    cpu_trend, cpu_rate = _trend_analysis(list(recent_history), "cpu_millicores")
    restart_trend, _ = _trend_analysis(list(recent_history), "restart_count")

    # Determine overall trend
    if cpu_trend == "rising" or restart_trend == "rising":
        overall_trend = "rising"
    elif cpu_trend == "falling" and restart_trend != "rising":
        overall_trend = "recovering"
    else:
        overall_trend = "stable"

    time_to_failure = _estimate_time_to_failure(risk_score, overall_trend, list(recent_history))

    return risk_score, predicted_failure_type, rationale, overall_trend, time_to_failure


def build_prediction_event(
    service: str,
    run_id: str,
    scenario: str,
    snapshot_time: Any,
    risk_score: float,
    predicted_failure_type: str,
    rationale: List[str],
    current: Dict[str, Any],
    trend: str,
    time_to_failure: str,
) -> Dict[str, Any]:
    if risk_score >= 0.80:
        risk_level = "critical"
    elif risk_score >= 0.60:
        risk_level = "high"
    elif risk_score >= 0.40:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "event_type": "prediction_risk",
        "agent": "prediction_agent",
        "service": service,
        "run_id": run_id,
        "scenario": scenario,
        "snapshot_time": snapshot_time,
        "predicted_failure": predicted_failure_type,
        "probability": risk_score,
        "trend": trend,
        "time_to_failure": time_to_failure,
        "prediction_window": "next_snapshot",
        "risk_score": risk_score,
        "risk_level": risk_level,
        "predicted_failure_type": predicted_failure_type,
        "rationale": rationale,
        "current_flags": current.get("anomaly_flags", []),
        "evidence": current.get("evidence", []),
        "ml_enabled": SKLEARN_AVAILABLE,
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
        f"[Prediction] Starting agent | consume={topics_to_subscribe} | "
        f"publish={TOPICS['agent_prediction_risks']} | ML={SKLEARN_AVAILABLE}"
    )

    history: Dict[Tuple[str, str], Deque[Dict[str, Any]]] = defaultdict(
        lambda: deque(maxlen=8)
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

            risk_score, predicted_failure_type, rationale, trend, time_to_failure = compute_risk(
                current, previous, list(recent)
            )

            if risk_score < 0.35:
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
                trend=trend,
                time_to_failure=time_to_failure,
            )

            try:
                future = producer.send(
                    TOPICS["agent_prediction_risks"], value=event, key=service
                )
                future.get(timeout=10)
                print(
                    f"[Prediction] Risk published for {service}: "
                    f"score={risk_score}, trend={trend}, ttf={time_to_failure}"
                )
            except (KafkaTimeoutError, NoBrokersAvailable) as exc:
                print(f"[ERROR] Kafka broker unavailable: {exc}")
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
```

---

## Prediction Event Schema (Output)

```json
{
  "event_type": "prediction_risk",
  "agent": "prediction_agent",
  "service": "cartservice",
  "run_id": "run_001",
  "scenario": "cpu_spike",
  "predicted_failure": "cpu_saturation",
  "probability": 0.78,
  "trend": "rising",
  "time_to_failure": "5-15 minutes",
  "risk_score": 0.78,
  "risk_level": "high",
  "rationale": [
    "CPU rising from 400 to 950 millicores (+137%)",
    "CPU critically high at 950 millicores",
    "Isolation Forest anomaly score: 0.71 (+0.18 risk)"
  ],
  "ml_enabled": true
}
```

---

## Risk Score Breakdown

| Signal | Max Contribution |
|---|---|
| CPU spike (>25% increase) | +0.35 |
| CPU critically high (≥800m) | +0.20 |
| Restart count increase | +0.25 |
| Elevated restarts (≥5) | +0.15 |
| Failed pod create events | +0.30 |
| Log error increase | +0.20 |
| HTTP error increase | +0.20 |
| Latency spike (>30% increase) | +0.20 |
| Pod in non-running state | +0.25 |
| Isolation Forest (additive) | +0.25 |
| Persistent anomalies (3 consecutive) | +0.15 |
