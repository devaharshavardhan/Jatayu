from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import List

from normalizer.rca.rca_agent import RCAResult, find_root_cause_from_files


def _format_result(result: RCAResult) -> str:
    return (
        f"affected={result.affected_service} "
        f"root_cause={result.root_cause_service} "
        f"status={result.root_cause_status} "
        f"severity={result.root_cause_severity:.2f} "
        f"path={' -> '.join(result.path)}"
    )


def run(service_health_file: str, dependency_graph_file: str, target_service: str | None) -> List[RCAResult]:
    return find_root_cause_from_files(
        service_health_file=service_health_file,
        dependency_graph_file=dependency_graph_file,
        target_service=target_service,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run dependency-aware RCA on normalized health output.")
    parser.add_argument("--service-health", required=True, help="Path to service_health.json")
    parser.add_argument("--dependency-graph", required=True, help="Path to dependency_graph.json")
    parser.add_argument("--target-service", default=None, help="Optional specific impacted service")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    results = run(args.service_health, args.dependency_graph, args.target_service)

    if args.json:
        import json

        payload = [asdict(result) for result in results]
        print(json.dumps(payload, indent=2))
    else:
        for result in results:
            print(_format_result(result))

    if not results:
        print("No impacted services found for RCA.")
