from __future__ import annotations

import json
from typing import Dict, List


DependencyGraph = Dict[str, List[str]]


def load_dependency_graph(file_path: str) -> DependencyGraph:
    """Load a dependency graph from JSON and normalize shape to dict[str, list[str]]."""
    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("Dependency graph must be a JSON object.")

    graph: DependencyGraph = {}
    for service, deps in raw.items():
        service_name = str(service).strip()
        if not service_name:
            continue

        if deps is None:
            graph[service_name] = []
            continue

        if not isinstance(deps, list):
            raise ValueError(f"Dependencies for '{service_name}' must be a list.")

        normalized = [str(dep).strip() for dep in deps if str(dep).strip()]
        graph[service_name] = sorted(set(normalized))

    # Ensure every referenced dependency appears as a node for simpler traversal.
    for deps in list(graph.values()):
        for dep in deps:
            graph.setdefault(dep, [])

    return graph
