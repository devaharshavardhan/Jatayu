from __future__ import annotations

from datetime import datetime, timezone


def extract_service_name(pod_name: str) -> str:
    parts = pod_name.split("-")
    if len(parts) >= 3:
        return "-".join(parts[:-2])
    return pod_name


def parse_cpu_to_millicores(value: str) -> int:
    value = value.strip()
    if value.endswith("m"):
        return int(value[:-1])
    return int(float(value) * 1000)


def parse_memory_to_mib(value: str) -> int:
    value = value.strip()
    if value.endswith("Ki"):
        return int(float(value[:-2]) / 1024)
    if value.endswith("Mi"):
        return int(float(value[:-2]))
    if value.endswith("Gi"):
        return int(float(value[:-2]) * 1024)
    return int(value)


def parse_k8s_human_date(text: str) -> datetime:
    # Example: "Mon Mar 24 11:35:48 UTC 2026"
    return datetime.strptime(text.strip(), "%a %b %d %H:%M:%S %Z %Y").replace(tzinfo=timezone.utc)