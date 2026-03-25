from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from normalizer.models import LogEvent


def classify_plain_log(service: str, line: str) -> tuple[str, str, Optional[str]]:
    text = line.lower()

    if "redis is starting" in text:
        return "info", "startup", None
    if "checking" in text and "health" in text:
        return "info", "health_check", None
    if "additemasync" in text:
        return "info", "cart_operation", "AddItemAsync"
    if "getcartasync" in text:
        return "info", "cart_operation", "GetCartAsync"
    if "error" in text or "exception" in text or "failed" in text or "timeout" in text:
        return "error", "error", None

    return "info", "generic", None


def parse_json_log(service: str, line: str, snapshot_time: datetime) -> Optional[LogEvent]:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    ts = data.get("timestamp")
    parsed_ts = None
    if ts:
        try:
            parsed_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            parsed_ts = None

    status_code = data.get("http.resp.status")
    latency_ms = data.get("http.resp.took_ms")
    message = data.get("message", "")
    severity = data.get("severity", "info")
    path = data.get("http.req.path")
    method = data.get("http.req.method")

    event_type = "generic"
    if message == "request complete":
        event_type = "http_request_complete"

    return LogEvent(
        service=service,
        timestamp=parsed_ts,
        severity=severity,
        message=message,
        event_type=event_type,
        status_code=status_code,
        latency_ms=latency_ms,
        path=path,
        method=method,
        raw=data,
        snapshot_time=snapshot_time,
    )


def parse_log_file(file_path: str, snapshot_time: datetime) -> List[LogEvent]:
    service = Path(file_path).stem
    records: List[LogEvent] = []

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            json_record = parse_json_log(service, line, snapshot_time)
            if json_record:
                records.append(json_record)
                continue

            severity, event_type, operation = classify_plain_log(service, line)
            records.append(
                LogEvent(
                    service=service,
                    timestamp=None,
                    severity=severity,
                    message=line,
                    event_type=event_type,
                    operation=operation,
                    snapshot_time=snapshot_time,
                )
            )

    return records