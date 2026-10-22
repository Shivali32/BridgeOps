"""Run with python -m app.messaging.publisher."""

import json
import logging
import os
import signal
import threading
from datetime import timedelta

from confluent_kafka import KafkaException, Producer
from sqlalchemy import select

from app.db import SessionLocal
from app.messaging.contracts import topic
from app.models.messaging import OutboxEvent
from app.services.workflow import now

log = logging.getLogger(__name__)


def make_producer():
    return Producer(
        {
            "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092"),
            "client.id": "bridgops-outbox",
            "enable.idempotence": True,
            "acks": "all",
            "delivery.timeout.ms": 5000,
            "request.timeout.ms": 3000,
            "allow.auto.create.topics": False,
        }
    )


def publish_one(db, producer):
    event = db.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.published_at.is_(None),
            OutboxEvent.next_attempt_at <= now(),
        )
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if event is None:
        db.rollback()
        return False
    delivered = []
    try:
        producer.produce(
            topic(),
            key=f"{event.tenant_id}:{event.execution_id}",
            value=json.dumps(event.payload).encode(),
            on_delivery=lambda error, message: delivered.append(error),
        )
        remaining = producer.flush(6)
        if remaining or not delivered or delivered[0] is not None:
            raise RuntimeError("Kafka delivery was not confirmed")
        event.published_at, event.last_error = now(), None
    except (KafkaException, BufferError, RuntimeError):
        # The broker may have accepted the record before the response was lost.
        # Reusing its event ID makes later deliveries safe at the consumer.
        event.last_error = "Kafka delivery unavailable; retry scheduled"
        event.next_attempt_at = now() + timedelta(
            seconds=min(60, 2 ** min(event.attempts + 1, 6))
        )
        log.warning("Kafka publish deferred for event %s", event.id)
    event.attempts += 1
    db.commit()
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    producer = make_producer()
    while not stop.is_set():
        with SessionLocal() as db:
            had_work = publish_one(db, producer)
        if not had_work:
            stop.wait(0.5)
    producer.flush(6)


if __name__ == "__main__":
    main()
