from __future__ import annotations

import json
import re
from datetime import datetime
from typing import List

from normalizer.models import PodStatus
from normalizer.utils import extract_service_name


def _parse_restart_count(value: str) -> int:
    match = re.match(r"^(\d+)", value.strip())
    if not match:
        return 0
    return int(match.group(1))


def _parse_legacy_pod_table(content: str, snapshot_time: datetime) -> List[PodStatus]:
    records: List[PodStatus] = []

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines or lines[0].lower().startswith("no resources found"):
        return records

    # Skip header row: NAME READY STATUS RESTARTS ...
    for line in lines[1:]:
        # Split on 2+ spaces to preserve values like "7 (5m37s ago)".
        parts = re.split(r"\s{2,}", line)
        if len(parts) < 4:
            continue

        pod_name = parts[0]
        ready = parts[1]
        phase = parts[2]
        restarts = _parse_restart_count(parts[3])

        age = parts[4] if len(parts) > 4 else None
        ip = parts[5] if len(parts) > 5 and parts[5] != "<none>" else None
        node = parts[6] if len(parts) > 6 and parts[6] != "<none>" else None

        records.append(
            PodStatus(
                service=extract_service_name(pod_name),
                pod=pod_name,
                ready=ready,
                status=phase,
                restarts=restarts,
                age=age,
                ip=ip,
                node=node,
                snapshot_time=snapshot_time,
            )
        )

    return records


def parse_pod_status_json(file_path: str, snapshot_time: datetime) -> List[PodStatus]:
    records: List[PodStatus] = []

    with open(file_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    stripped = content.lstrip()
    if not stripped or stripped.lower().startswith("no resources found"):
        return records

    if not stripped.startswith(("{", "[")):
        return _parse_legacy_pod_table(content, snapshot_time)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid pod status JSON in '{file_path}'. Expected output from 'kubectl get pods -o json'."
        ) from exc

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        try:
            items = data.get("items", [])
        except AttributeError:
            items = []
    else:
        items = []

    if not isinstance(items, list):
        return records

    for item in items:
        if not isinstance(item, dict):
            continue

        metadata = item.get("metadata", {})
        status = item.get("status", {})
        spec = item.get("spec", {})

        pod_name = str(metadata.get("name", "")).strip()
        if not pod_name:
            continue

        service = extract_service_name(pod_name)

        container_statuses = status.get("containerStatuses", [])
        if not isinstance(container_statuses, list):
            container_statuses = []

        restart_count = 0
        ready_count = 0
        total_count = 0

        for container in container_statuses:
            if not isinstance(container, dict):
                continue

            total_count += 1
            try:
                restart_count += int(container.get("restartCount", 0) or 0)
            except (TypeError, ValueError):
                # Ignore malformed restart counters and keep parsing the snapshot.
                pass
            if bool(container.get("ready", False)):
                ready_count += 1

        records.append(
            PodStatus(
                service=service,
                pod=pod_name,
                ready=f"{ready_count}/{total_count}",
                status=str(status.get("phase", "Unknown")),
                restarts=restart_count,
                ip=status.get("podIP"),
                node=spec.get("nodeName"),
                snapshot_time=snapshot_time,
            )
        )

    return records
