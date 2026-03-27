"""Kafka connectivity health check for local dev."""
from __future__ import annotations

import sys
from typing import Optional

from kafka import KafkaConsumer
from kafka.errors import KafkaError, NoBrokersAvailable, KafkaTimeoutError

from messaging.config import get_bootstrap_servers, get_common_client_id


def check_kafka_connection(timeout_seconds: int = 5) -> bool:
    bootstrap = get_bootstrap_servers()
    try:
        consumer = KafkaConsumer(
            bootstrap_servers=bootstrap,
            client_id=get_common_client_id("healthcheck"),
            request_timeout_ms=timeout_seconds * 1000,
            metadata_max_age_ms=timeout_seconds * 1000,
            consumer_timeout_ms=timeout_seconds * 1000,
        )
        consumer.topics()  # triggers metadata fetch
        consumer.close()
        print(f"[Healthcheck] Kafka reachable at {bootstrap}")
        return True
    except (NoBrokersAvailable, KafkaTimeoutError) as exc:
        print(f"[ERROR] Kafka broker unavailable at {bootstrap}: {exc}")
    except KafkaError as exc:
        print(f"[ERROR] Kafka metadata fetch failed at {bootstrap}: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Unexpected error checking Kafka at {bootstrap}: {exc}")
    return False


def _main(argv: Optional[list[str]] = None) -> int:
    ok = check_kafka_connection()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main())
