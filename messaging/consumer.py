"""Kafka consumer factory with centralized config."""
from __future__ import annotations

import json
from typing import Any

from kafka import KafkaConsumer

from messaging.config import get_bootstrap_servers, get_common_client_id


def get_consumer(*topics: str, group_id: str, auto_offset_reset: str = "latest") -> KafkaConsumer:
    return KafkaConsumer(
        *topics,
        bootstrap_servers=get_bootstrap_servers(),
        client_id=get_common_client_id("consumer"),
        group_id=group_id,
        auto_offset_reset=auto_offset_reset,
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
        request_timeout_ms=30000,
        session_timeout_ms=10000,
        heartbeat_interval_ms=3000,
    )
