from __future__ import annotations

from datetime import datetime

from normalizer.utils import parse_k8s_human_date


def parse_time_file(file_path: str) -> datetime:
    with open(file_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    return parse_k8s_human_date(raw)