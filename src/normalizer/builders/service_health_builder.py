from __future__ import annotations

from typing import List

from normalizer.models import ServiceFeatures, ServiceHealth


def build_service_health(features: List[ServiceFeatures]) -> List[ServiceHealth]:
    results: List[ServiceHealth] = []

    for f in features:
        score = 0.0

        score += min(f.warning_event_count * 0.1, 0.3)
        score += min(f.unhealthy_event_count * 0.2, 0.4)
        score += min(f.failed_create_count * 0.3, 0.5)
        score += min(f.log_error_count * 0.1, 0.3)
        score += min(f.http_error_count * 0.05, 0.3)

        if f.avg_latency_ms and f.avg_latency_ms > 150:
            score += 0.2
        if f.restart_count > 0:
            score += 0.2
        if f.pod_status and f.pod_status not in {"Running", "Completed"}:
            score += 0.3

        score = min(score, 1.0)

        if score >= 0.75:
            status = "failed"
        elif score >= 0.3:
            status = "degraded"
        else:
            status = "healthy"

        results.append(
            ServiceHealth(
                service=f.service,
                snapshot_time=f.snapshot_time,
                status=status,
                severity_score=round(score, 2),
                anomaly_flags=f.anomaly_flags,
                evidence=f.evidence,
            )
        )

    return results