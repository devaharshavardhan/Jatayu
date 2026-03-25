from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from normalizer.models import K8sEvent, LogEvent, PodMetric, PodStatus, ServiceFeatures


LATENCY_SPIKE_THRESHOLD_MS = 150.0
HTTP_ERROR_RATE_THRESHOLD = 0.1
RESTART_SPIKE_THRESHOLD = 3


def build_service_features(
    snapshot_time: datetime,
    pod_metrics: List[PodMetric],
    pod_statuses: List[PodStatus],
    k8s_events: List[K8sEvent],
    log_events: List[LogEvent],
) -> List[ServiceFeatures]:

    services: Dict[str, ServiceFeatures] = {}

    def get_service(service_name: str) -> ServiceFeatures:
        if service_name not in services:
            services[service_name] = ServiceFeatures(
                service=service_name,
                snapshot_time=snapshot_time
            )
        return services[service_name]

    # -------------------------
    # 1. METRICS
    # -------------------------
    for metric in pod_metrics:
        s = get_service(metric.service)
        s.cpu_millicores = metric.cpu_millicores
        s.memory_mib = metric.memory_mib

    # -------------------------
    # 2. POD STATUS
    # -------------------------
    for pod in pod_statuses:
        s = get_service(pod.service)
        s.pod_status = pod.status
        s.ready = pod.ready
        s.restart_count += pod.restarts

        if pod.ready and "/" in pod.ready:
            try:
                ready_count, total_count = (int(x) for x in pod.ready.split("/", 1))
                if total_count > 0 and ready_count < total_count:
                    s.anomaly_flags.append("readiness_probe_failed")
                    s.evidence.append("Readiness probe failure observed")
            except ValueError:
                # Keep normalization resilient when readiness is malformed.
                pass

    # -------------------------
    # 3. EVENTS
    # -------------------------
    for event in k8s_events:
        if not event.service:
            continue

        s = get_service(event.service)

        reason = (event.reason or "").lower()
        event_category = (event.event_category or "").lower()

        if event.severity == "warning":
            s.warning_event_count += 1

        if event_category == "probe_failure" or "unhealthy" in reason:
            s.unhealthy_event_count += 1
            s.anomaly_flags.append("readiness_probe_failed")
            s.evidence.append("Readiness probe failure observed")

        if event_category == "create_failure" or "failedcreate" in reason or "failed create" in reason:
            s.failed_create_count += 1
            s.anomaly_flags.append("pod_create_failure")
            s.evidence.append("Pod creation failure detected")

        if event_category == "crash_loop":
            s.anomaly_flags.append("crash_loop")
            s.evidence.append("Crash loop/backoff condition observed")

        if event_category == "pod_termination" or "killing" in reason:
            s.anomaly_flags.append("pod_killed")
            s.evidence.append("Pod termination event detected")

    # -------------------------
    # 4. LOGS
    # -------------------------
    latency_store: Dict[str, List[float]] = defaultdict(list)

    for log in log_events:
        s = get_service(log.service)

        severity = (log.severity or "").lower()

        if severity in {"error", "fatal"}:
            s.log_error_count += 1
            s.evidence.append("Error log detected")

        elif severity == "warning":
            s.log_warning_count += 1

        else:
            s.success_log_count += 1

        # HTTP signals
        if log.event_type == "http_request_complete":

            if log.status_code is not None:
                if 200 <= log.status_code < 400:
                    s.http_success_count += 1
                else:
                    s.http_error_count += 1
                    s.anomaly_flags.append("http_errors")
                    s.evidence.append("HTTP error responses observed")

            if log.latency_ms is not None:
                latency_store[log.service].append(float(log.latency_ms))

    # -------------------------
    # 5. LATENCY ANALYSIS
    # -------------------------
    for service_name, latencies in latency_store.items():
        s = get_service(service_name)

        if latencies:
            avg = sum(latencies) / len(latencies)
            s.avg_latency_ms = avg

            if avg > LATENCY_SPIKE_THRESHOLD_MS:
                s.anomaly_flags.append("latency_spike")
                s.evidence.append(f"High latency detected ({int(avg)} ms)")

    # -------------------------
    # 6. RESTART ANALYSIS
    # -------------------------
    for s in services.values():
        if s.restart_count > RESTART_SPIKE_THRESHOLD:
            s.anomaly_flags.append("high_restarts")
            s.evidence.append(f"{s.restart_count} restarts detected")

        total_http = s.http_success_count + s.http_error_count
        if total_http > 0:
            error_rate = s.http_error_count / total_http
            if error_rate >= HTTP_ERROR_RATE_THRESHOLD:
                s.anomaly_flags.append("http_errors")
                s.evidence.append(
                    f"HTTP errors observed ({s.http_error_count}/{total_http}, {error_rate:.0%})"
                )

    # -------------------------
    # 7. CLEANUP
    # -------------------------
    for s in services.values():
        s.anomaly_flags = sorted(set(s.anomaly_flags))
        s.evidence = sorted(set(s.evidence))

    return list(services.values())