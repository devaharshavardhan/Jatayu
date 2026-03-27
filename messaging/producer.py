"""Reusable Kafka producer factory with centralized config."""
from __future__ import annotations

import json
from typing import Optional

from kafka import KafkaProducer

from messaging.config import get_bootstrap_servers, get_common_client_id


def _serialize_value(value) -> bytes:
    return json.dumps(value).encode("utf-8")


def _serialize_key(key: Optional[str]) -> Optional[bytes]:
    return str(key).encode("utf-8") if key is not None else None


def get_producer() -> KafkaProducer:
    """Create a KafkaProducer with sensible defaults for local dev."""
    return KafkaProducer(
        bootstrap_servers=get_bootstrap_servers(),
        client_id=get_common_client_id("producer"),
        acks="all",
        retries=3,
        linger_ms=5,
        request_timeout_ms=15000,
        max_block_ms=15000,
        metadata_max_age_ms=30000,
        value_serializer=_serialize_value,
        key_serializer=_serialize_key,
    )
