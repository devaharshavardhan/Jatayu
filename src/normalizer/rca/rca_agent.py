from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

from normalizer.models import ServiceHealth
from normalizer.rca.dependency_graph_loader import DependencyGraph, load_dependency_graph


_STATUS_RANK = {
    "healthy": 0,
    "degraded": 1,
    "failed": 2,
}


@dataclass(frozen=True)
class RCAResult:
    affected_service: str
    root_cause_service: str
    root_cause_status: str
    root_cause_severity: float
    path: List[str]


def _load_service_health(file_path: str) -> List[ServiceHealth]:
    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        raise ValueError("service_health.json must contain a list of service health records.")

    records: List[ServiceHealth] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        records.append(ServiceHealth.model_validate(item))

    return records


def _is_more_severe(candidate: ServiceHealth, current: ServiceHealth) -> bool:
    candidate_rank = _STATUS_RANK.get(candidate.status, 0)
    current_rank = _STATUS_RANK.get(current.status, 0)

    if candidate_rank != current_rank:
        return candidate_rank > current_rank

    if candidate.severity_score != current.severity_score:
        return candidate.severity_score > current.severity_score

    # Stable tie-breaker to keep deterministic output.
    return candidate.service < current.service


def _find_worst_dependency(
    service: str,
    health_map: Dict[str, ServiceHealth],
    graph: DependencyGraph,
) -> tuple[ServiceHealth, List[str]]:
    start = health_map[service]
    best = start
    best_path = [service]

    visited: Set[str] = set()

    def dfs(node: str, path: List[str]) -> None:
        nonlocal best, best_path
        if node in visited:
            return

        visited.add(node)
        for dep in graph.get(node, []):
            dep_health = health_map.get(dep)
            if dep_health is None:
                continue

            dep_path = path + [dep]
            if _is_more_severe(dep_health, best):
                best = dep_health
                best_path = dep_path

            dfs(dep, dep_path)

    dfs(service, [service])
    return best, best_path


def find_root_cause(
    service_health: Iterable[ServiceHealth],
    dependency_graph: DependencyGraph,
    target_service: Optional[str] = None,
) -> List[RCAResult]:
    """Find likely root causes by traversing dependency chains for degraded/failed services."""
    health_map = {record.service: record for record in service_health}

    impacted = [
        service
        for service, record in health_map.items()
        if record.status in {"degraded", "failed"}
    ]

    if target_service:
        if target_service not in health_map:
            return []
        impacted = [target_service]

    impacted.sort(
        key=lambda svc: (
            _STATUS_RANK.get(health_map[svc].status, 0),
            health_map[svc].severity_score,
            svc,
        ),
        reverse=True,
    )

    results: List[RCAResult] = []
    for service in impacted:
        worst, path = _find_worst_dependency(service, health_map, dependency_graph)
        results.append(
            RCAResult(
                affected_service=service,
                root_cause_service=worst.service,
                root_cause_status=worst.status,
                root_cause_severity=worst.severity_score,
                path=path,
            )
        )

    return results


def find_root_cause_from_files(
    service_health_file: str,
    dependency_graph_file: str,
    target_service: Optional[str] = None,
) -> List[RCAResult]:
    service_health = _load_service_health(service_health_file)
    dependency_graph = load_dependency_graph(dependency_graph_file)
    return find_root_cause(service_health, dependency_graph, target_service)
