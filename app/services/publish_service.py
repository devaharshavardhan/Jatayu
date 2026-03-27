from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from messaging.publisher import publish_snapshot


def publish_snapshot_dir(path: Path) -> dict:
    return publish_snapshot(path)


def publish_run_snapshots(run_dir: Path, start_index: int = 0, limit: Optional[int] = None) -> dict:
    snapshot_dirs: List[Path] = sorted([p for p in run_dir.iterdir() if p.is_dir()])
    if limit is not None:
        snapshot_dirs = snapshot_dirs[start_index : start_index + limit]
    else:
        snapshot_dirs = snapshot_dirs[start_index:]

    total_sent = 0
    total_failed = 0
    per_snapshot = {}
    for snap in snapshot_dirs:
        summary = publish_snapshot_dir(snap)
        per_snapshot[snap.name] = summary
        total_sent += summary.get("sent", 0)
        total_failed += summary.get("failed", 0)
    return {"sent": total_sent, "failed": total_failed, "snapshots": per_snapshot}
