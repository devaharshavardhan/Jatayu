from __future__ import annotations

import argparse
from pathlib import Path

from normalizer.snapshot_normalizer import normalize_snapshot, save_normalized_snapshot


def normalize_run(dataset_root: str, scenario: str, run_id: str, output_root: str) -> None:
    run_dir = Path(dataset_root) / scenario / run_id
    output_dir = Path(output_root) / scenario / run_id

    snapshot_dirs = sorted(
        [p for p in run_dir.iterdir() if p.is_dir() and p.name.startswith("snapshot_")]
    )

    for snapshot_dir in snapshot_dirs:
        normalized = normalize_snapshot(str(snapshot_dir), scenario, run_id)
        save_normalized_snapshot(normalized, str(output_dir / snapshot_dir.name))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", default="dataset")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", default="normalized")
    args = parser.parse_args()

    normalize_run(
        dataset_root=args.dataset_root,
        scenario=args.scenario,
        run_id=args.run_id,
        output_root=args.output_root,
    )