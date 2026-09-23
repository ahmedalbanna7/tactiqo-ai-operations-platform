"""Reference-only RabbitMQ topology for isolated F5 workload families."""

import json

import aio_pika

from tactiqo.jobs.domain.models import Job, JobKind

JOB_EXCHANGE = "tactiqo.jobs.v1"
JOB_DEAD_EXCHANGE = "tactiqo.jobs.v1.dead"

QUEUE_BY_KIND: dict[JobKind, str] = {
    JobKind.DOCUMENT_OCR: "jobs.document-ocr.v1",
    JobKind.MEDIA: "jobs.media.v1",
    JobKind.REPORT_BI: "jobs.report-bi.v1",
    JobKind.INTEGRATION_AUTOMATION: "jobs.integration-automation.v1",
    JobKind.RISK_REVIEW: "jobs.risk-review.v1",
}


async def declare_job_topology(
    channel: aio_pika.abc.AbstractChannel,
) -> dict[JobKind, aio_pika.abc.AbstractQueue]:
    """Declare one durable queue and DLQ per workload family."""
    exchange = await channel.declare_exchange(
        JOB_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
    )
    dead_exchange = await channel.declare_exchange(
        JOB_DEAD_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
    )
    queues: dict[JobKind, aio_pika.abc.AbstractQueue] = {}
    for kind, name in QUEUE_BY_KIND.items():
        dead_name = f"{name}.dlq"
        dead_queue = await channel.declare_queue(dead_name, durable=True)
        await dead_queue.bind(dead_exchange, routing_key=dead_name)
        queue = await channel.declare_queue(
            name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": JOB_DEAD_EXCHANGE,
                "x-dead-letter-routing-key": dead_name,
                "x-max-priority": 10,
            },
        )
        await queue.bind(exchange, routing_key=kind.value)
        queues[kind] = queue
    return queues


class RabbitJobPublisher:
    """Publish identifiers and signed authorization only; data remains in MinIO."""

    def __init__(self, rabbitmq_url: str) -> None:
        """Configure the broker without retaining input content."""
        self._rabbitmq_url = rabbitmq_url

    async def publish(self, job: Job, work_envelope: str) -> None:
        """Publish a persistent deduplicable reference-only notification."""
        connection = await aio_pika.connect_robust(self._rabbitmq_url)
        async with connection:
            channel = await connection.channel(publisher_confirms=True)
            await declare_job_topology(channel)
            exchange = await channel.get_exchange(JOB_EXCHANGE)
            body = json.dumps(
                {
                    "job_id": str(job.id),
                    "organization_id": job.organization_id,
                    "kind": job.kind.value,
                    "risk": job.risk.value,
                    "input_reference": job.input_reference,
                    "work_envelope": work_envelope,
                },
                separators=(",", ":"),
            ).encode()
            await exchange.publish(
                aio_pika.Message(
                    body=body,
                    message_id=str(job.id),
                    correlation_id=str(job.run_id),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    priority=max(0, min(10, job.priority // 10)),
                ),
                routing_key=job.kind.value,
                mandatory=True,
            )
