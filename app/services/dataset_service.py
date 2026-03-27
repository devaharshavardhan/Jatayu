from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

NORMALIZED_ROOT = Path(__file__).resolve().parent.parent.parent / "normalized"

SCENARIOS = [
    "c_pod_kill",
    "c_cpu_spike",
    "c_network_delay",
    "c_redis_failure",
]


def list_scenarios() -> List[str]:
    return [s for s in SCENARIOS if (NORMALIZED_ROOT / s).exists()]


def list_runs(scenario: str) -> List[str]:
    base = NORMALIZED_ROOT / scenario
    if not base.exists():
        return []
    return sorted([p.name for p in base.iterdir() if p.is_dir()])


def list_snapshots(scenario: str, run_id: str) -> List[str]:
    run_path = NORMALIZED_ROOT / scenario / run_id
    if not run_path.exists():
        return []
    return sorted([p.name for p in run_path.iterdir() if p.is_dir()])


def snapshot_path(scenario: str, run_id: str, snapshot_id: str) -> Path:
    return NORMALIZED_ROOT / scenario / run_id / snapshot_id


FILES = [
    "snapshot_context.json",
    "k8s_events.json",
    "log_events.json",
    "pod_metrics.json",
    "pod_status.json",
    "service_features.json",
    "service_health.json",
]


def load_snapshot_files(scenario: str, run_id: str, snapshot_id: str) -> Dict[str, Optional[Dict]]:
    base = snapshot_path(scenario, run_id, snapshot_id)
    result: Dict[str, Optional[Dict]] = {}
    for fname in FILES:
        fpath = base / fname
        if not fpath.exists():
            result[fname] = None
            continue
        try:
            result[fname] = json.loads(fpath.read_text())
        except json.JSONDecodeError:
            result[fname] = {"error": "invalid_json"}
    return result
