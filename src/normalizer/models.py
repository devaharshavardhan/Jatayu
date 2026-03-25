from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SnapshotContext(BaseModel):
    scenario: str
    run_id: str
    snapshot_id: str
    snapshot_time: datetime


class PodMetric(BaseModel):
    service: str
    pod: str
    cpu_millicores: int
    memory_mib: int
    snapshot_time: datetime


class PodStatus(BaseModel):
    service: str
    pod: str
    ready: str
    status: str
    restarts: int
    age: Optional[str] = None
    ip: Optional[str] = None
    node: Optional[str] = None
    snapshot_time: datetime


class K8sEvent(BaseModel):
    service: Optional[str] = None
    object_kind: Optional[str] = None
    object_name: Optional[str] = None
    event_type: Optional[str] = None   # Normal / Warning
    reason: Optional[str] = None
    message: str
    event_category: Optional[str] = None
    severity: Literal["info", "warning", "error"] = "info"
    snapshot_time: datetime


class LogEvent(BaseModel):
    service: str
    timestamp: Optional[datetime] = None
    severity: str = "info"
    message: str
    event_type: str = "generic"
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    path: Optional[str] = None
    method: Optional[str] = None
    operation: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None
    snapshot_time: datetime


class ServiceFeatures(BaseModel):
    service: str
    snapshot_time: datetime

    cpu_millicores: Optional[int] = None
    memory_mib: Optional[int] = None

    pod_status: Optional[str] = None
    ready: Optional[str] = None
    restart_count: int = 0

    warning_event_count: int = 0
    unhealthy_event_count: int = 0
    failed_create_count: int = 0

    log_error_count: int = 0
    log_warning_count: int = 0
    success_log_count: int = 0

    http_success_count: int = 0
    http_error_count: int = 0
    avg_latency_ms: Optional[float] = None

    anomaly_flags: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)


class ServiceHealth(BaseModel):
    service: str
    snapshot_time: datetime
    status: Literal["healthy", "degraded", "failed"]
    severity_score: float
    anomaly_flags: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)


class NormalizedSnapshot(BaseModel):
    context: SnapshotContext
    pod_metrics: List[PodMetric]
    pod_statuses: List[PodStatus]
    k8s_events: List[K8sEvent]
    log_events: List[LogEvent]
    service_features: List[ServiceFeatures]
    service_health: List[ServiceHealth]