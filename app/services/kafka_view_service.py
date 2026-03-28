from __future__ import annotations

import json
from typing import Any, Dict, List

from kafka import KafkaConsumer
from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

from messaging.config import get_bootstrap_servers, get_common_client_id

SAFE_TOPICS = {
    "jatayu.snapshot.context",
    "jatayu.telemetry.service_features",
    "jatayu.telemetry.service_health",
    "jatayu.agent.monitoring.alerts",
    "jatayu.agent.monitoring.incidents",
    "jatayu.agent.prediction.risks",
    "jatayu.agent.rca.results",
    "jatayu.agent.decision.intents",
    "jatayu.agent.remediation.results",
    "jatayu.agent.reporting.incidents",
}


def get_recent_messages(topic: str, max_messages: int = 20) -> Dict[str, Any]:
    if topic not in SAFE_TOPICS:
        return {"error": "topic_not_allowed", "messages": []}

    bootstrap = get_bootstrap_servers()
    messages: List[Dict[str, Any]] = []
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap,
            client_id=get_common_client_id("viewer"),
            group_id=None,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
            consumer_timeout_ms=2000,
        )
        # Seek to near end to get recent messages
        consumer.poll(timeout_ms=100)
        for tp in consumer.assignment():
            end_offset = consumer.end_offsets([tp])[tp]
            start = max(0, end_offset - max_messages)
            consumer.seek(tp, start)

        for msg in consumer:
            if msg.value is not None:
                messages.append(msg.value)
            if len(messages) >= max_messages:
                break
        consumer.close()
        return {"messages": messages[-max_messages:]}
    except (NoBrokersAvailable, KafkaTimeoutError) as exc:
        return {"error": f"kafka_unavailable: {exc}", "messages": []}
    except KafkaError as exc:
        return {"error": f"kafka_error: {exc}", "messages": []}
    except Exception as exc:
        return {"error": f"unexpected_error: {exc}", "messages": []}
