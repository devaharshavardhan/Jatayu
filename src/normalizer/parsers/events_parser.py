from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from normalizer.models import K8sEvent
from normalizer.utils import extract_service_name


def classify_event(reason: Optional[str], message: str) -> tuple[str, str]:
    text = f"{reason or ''} {message}".lower()

    if "unhealthy" in text or "readiness probe failed" in text or "liveness probe failed" in text:
        return "probe_failure", "warning"
    if "failedcreate" in text or "failed create" in text:
        return "create_failure", "error"
    if "backoff" in text or "crashloopbackoff" in text:
        return "crash_loop", "error"
    if "killing" in text or "kill" in text:
        return "pod_termination", "warning"

    return "generic", "info"


_EVENT_LINE_PATTERN = re.compile(
    r"^\s*(?P<last_seen>.*?)\s+(?P<event_type>Normal|Warning)\s+(?P<reason>\S+)\s+(?P<object>\S+)\s+(?P<message>.+?)\s*$"
)


def detect_service_from_object(object_name: str) -> str:
    return extract_service_name(object_name)


def parse_events(file_path: str, snapshot_time: datetime) -> List[K8sEvent]:
    records = []

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    if len(lines) <= 1 or lines[0].lower().startswith("no resources found"):
        return records

    for line in lines[1:]:
        # Parse by anchoring on TYPE instead of naive whitespace split.
        match = _EVENT_LINE_PATTERN.match(line)
        if not match:
            continue

        event_type = match.group("event_type")
        reason = match.group("reason")
        obj = match.group("object")
        message = match.group("message")

        object_name = obj.split("/")[-1]
        object_kind = obj.split("/")[0] if "/" in obj else None

        service = extract_service_name(object_name)

        event_category, severity = classify_event(reason, message)

        records.append(
            K8sEvent(
                service=service,
                object_kind=object_kind,
                object_name=object_name,
                event_type=event_type,
                reason=reason,
                message=message,
                event_category=event_category,
                severity=severity,
                snapshot_time=snapshot_time,
            )
        )

    return records