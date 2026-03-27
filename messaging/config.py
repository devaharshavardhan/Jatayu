"""Kafka configuration helpers for JATAYU local dev."""
from __future__ import annotations

import os


def get_bootstrap_servers() -> str:
    """Return bootstrap servers from env or default localhost:9092."""
    return os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


def get_common_client_id(prefix: str) -> str:
    return f"jatayu-{prefix}"
