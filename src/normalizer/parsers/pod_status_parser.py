from __future__ import annotations

from datetime import datetime
from typing import List

from normalizer.models import PodStatus
from normalizer.parsers.pod_status_parser_json import parse_pod_status_json as _parse_pod_status_json_impl


def parse_pod_status(file_path: str, snapshot_time: datetime) -> List[PodStatus]:
    """Compatibility wrapper to preserve previous parser import paths."""
    return _parse_pod_status_json_impl(file_path, snapshot_time)


def parse_pod_status_json(file_path: str, snapshot_time: datetime) -> List[PodStatus]:
    """Backward-compatible alias for callers using old module path."""
    return _parse_pod_status_json_impl(file_path, snapshot_time)