from __future__ import annotations

from datetime import datetime
from typing import List

from normalizer.models import PodMetric
from normalizer.utils import extract_service_name, parse_cpu_to_millicores, parse_memory_to_mib


def parse_pod_metrics(file_path: str, snapshot_time: datetime) -> List[PodMetric]:
    records: List[PodMetric] = []

    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]

    if len(lines) <= 1:
        return records

    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue

        pod_name = parts[0]
        cpu = parts[1]
        memory = parts[2]

        records.append(
            PodMetric(
                service=extract_service_name(pod_name),
                pod=pod_name,
                cpu_millicores=parse_cpu_to_millicores(cpu),
                memory_mib=parse_memory_to_mib(memory),
                snapshot_time=snapshot_time,
            )
        )

    return records