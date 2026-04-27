import json
import logging

from aiokafka import AIOKafkaProducer

from .config import settings

logger = logging.getLogger(__name__)

_producer: AIOKafkaProducer | None = None


async def start() -> None:
    global _producer
    _producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
        enable_idempotence=True,
        acks="all",
    )
    await _producer.start()
    logger.info("Kafka producer started, brokers=%s", settings.kafka_bootstrap)


async def stop() -> None:
    if _producer is not None:
        await _producer.stop()


async def publish_raw(doc_id: str, payload: dict) -> None:
    assert _producer is not None
    await _producer.send_and_wait(settings.kafka_topic_raw, value=payload, key=doc_id)
