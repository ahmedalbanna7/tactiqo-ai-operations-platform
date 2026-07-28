"""RabbitMQ publisher for durable document parsing jobs."""

import json
from uuid import UUID

import aio_pika


async def declare_ingestion_topology(
    channel: aio_pika.abc.AbstractChannel,
    queue_name: str,
    dead_letter_queue_name: str,
) -> aio_pika.abc.AbstractQueue:
    """Declare one consistent queue/DLQ topology for publishers and workers."""
    dead_exchange = await channel.declare_exchange(
        f"{queue_name}.dead",
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )
    dead_queue = await channel.declare_queue(dead_letter_queue_name, durable=True)
    await dead_queue.bind(dead_exchange, routing_key=dead_letter_queue_name)
    return await channel.declare_queue(
        queue_name,
        durable=True,
        arguments={
            "x-dead-letter-exchange": dead_exchange.name,
            "x-dead-letter-routing-key": dead_letter_queue_name,
        },
    )


class RabbitMqIngestionPublisher:
    """Publish persistent, idempotent parse jobs with a configured DLQ."""

    def __init__(
        self,
        url: str,
        queue_name: str,
        dead_letter_queue_name: str,
    ) -> None:
        """Configure durable queue and dead-letter topology names."""
        self._url = url
        self._queue_name = queue_name
        self._dead_letter_queue_name = dead_letter_queue_name

    async def publish(self, document_id: UUID) -> None:
        """Declare topology and publish one persistent job."""
        connection = await aio_pika.connect_robust(self._url)
        async with connection:
            channel = await connection.channel(publisher_confirms=True)
            await declare_ingestion_topology(
                channel,
                self._queue_name,
                self._dead_letter_queue_name,
            )
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(
                        {"schema_version": 1, "document_id": str(document_id)}
                    ).encode(),
                    message_id=str(document_id),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                ),
                routing_key=self._queue_name,
            )
