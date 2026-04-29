import asyncio
import json
import logging
import signal

import asyncpg
from aiokafka import AIOKafkaConsumer
from prometheus_client import Counter, Histogram, start_http_server

from .config import settings
from .pipeline import process

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("transform")

processed = Counter(
    "transform_processed_total",
    "Processed messages",
    ["status", "doc_type"],
)
process_seconds = Histogram("transform_process_seconds", "Per-message processing seconds")

_KNOWN_STATUSES = ("loaded", "validated_with_errors", "error")
_KNOWN_DOC_TYPES = ("invoice", "act", "contract", "waybill", "upd", "payment_order", "unknown")
for _s in _KNOWN_STATUSES:
    for _t in _KNOWN_DOC_TYPES:
        processed.labels(status=_s, doc_type=_t)


def _asyncpg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+asyncpg://", "postgresql://")


async def consume(stop_event: asyncio.Event) -> None:
    pool = await asyncpg.create_pool(_asyncpg_dsn(settings.postgres_dsn), min_size=1, max_size=8)

    consumer = AIOKafkaConsumer(
        settings.kafka_topic_raw,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id=settings.kafka_group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
    )
    await consumer.start()
    logger.info("consumer started topic=%s group=%s", settings.kafka_topic_raw, settings.kafka_group_id)
    try:
        while not stop_event.is_set():
            try:
                batch = await asyncio.wait_for(consumer.getmany(timeout_ms=1000, max_records=32), timeout=2)
            except asyncio.TimeoutError:
                continue
            for tp, records in batch.items():
                for record in records:
                    try:
                        with process_seconds.time():
                            async with pool.acquire() as conn:
                                result = await process(conn, record.value)
                        processed.labels(
                            status=result["status"],
                            doc_type=result["doc_type"],
                        ).inc()
                    except Exception:
                        logger.exception("failed to process message offset=%s", record.offset)
                        processed.labels(status="error", doc_type="unknown").inc()
            if batch:
                await consumer.commit()
    finally:
        await consumer.stop()
        await pool.close()


async def amain() -> None:
    start_http_server(settings.metrics_port)
    logger.info("metrics on :%d/metrics", settings.metrics_port)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await consume(stop_event)


if __name__ == "__main__":
    asyncio.run(amain())
