from __future__ import annotations

import argparse
from pathlib import Path

from normalizer.rca.rca_agent import find_root_cause
from normalizer.rca.dependency_graph_loader import load_dependency_graph
from normalizer.snapshot_normalizer import normalize_snapshot


def run(snapshot_dir: str, scenario: str, run_id: str, dependency_graph_file: str) -> None:
    normalized = normalize_snapshot(snapshot_dir, scenario, run_id)
    dependency_graph = load_dependency_graph(dependency_graph_file)

    rca_results = find_root_cause(
        service_health=normalized.service_health,
        dependency_graph=dependency_graph,
    )

    for result in rca_results:
        print(
            f"affected={result.affected_service} "
            f"root_cause={result.root_cause_service} "
            f"status={result.root_cause_status} "
            f"severity={result.root_cause_severity:.2f} "
            f"path={' -> '.join(result.path)}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalize one snapshot and run dependency-aware RCA.")
    parser.add_argument("--snapshot-dir", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dependency-graph", default="dependency_graph.json")
    args = parser.parse_args()

    run(
        snapshot_dir=args.snapshot_dir,
        scenario=args.scenario,
        run_id=args.run_id,
        dependency_graph_file=args.dependency_graph,
    )
