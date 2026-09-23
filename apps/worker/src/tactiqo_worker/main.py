"""RabbitMQ consumer for isolated document parsing and indexing."""

import asyncio
import json
import time
from datetime import UTC, datetime
from uuid import UUID

import aio_pika
import uvicorn

from tactiqo.ai.application.bank import AIBank
from tactiqo.ai.application.ports import EmbeddingAdapter, LLMAdapter  # noqa: TC001
from tactiqo.ai.infrastructure.lm_studio import LMStudioAdapter
from tactiqo.ai.infrastructure.openai_compatible import OpenAICompatibleAdapter
from tactiqo.ai.infrastructure.repository import SqlAIProfileRepository
from tactiqo.ai.infrastructure.secrets import SqlEncryptedAISecretStore
from tactiqo.identity.infrastructure.context import SqlExecutionContextResolver
from tactiqo.ingestion.infrastructure.unstructured_parser import UnstructuredDocumentParser
from tactiqo.integrations.infrastructure.crypto import FernetCredentialCipher
from tactiqo.knowledge.application.telemetry import ObjectStorageMetrics
from tactiqo.knowledge.infrastructure.indexer import PgVectorKnowledgeIndexer
from tactiqo.knowledge.infrastructure.object_storage import MinioObjectStorage
from tactiqo.knowledge.infrastructure.queue import declare_ingestion_topology
from tactiqo.knowledge.infrastructure.repositories import SqlAlchemyKnowledgeRepository
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.database import create_database_engine, create_session_factory
from tactiqo.shared.infrastructure.settings import Settings
from tactiqo.shared.infrastructure.work_envelope import WorkEnvelopeSigner
from tactiqo_worker.telemetry import (
    WorkerMetrics,
    configure_storage_telemetry_logger,
    configure_worker_telemetry_logger,
    create_worker_metrics_app,
)


class IngestionWorker:
    """Process one document per delivery with bounded retry and safe failure codes."""

    def __init__(self, settings: Settings) -> None:
        """Compose worker-owned adapters from validated settings."""
        self._settings = settings
        self._logger = configure_worker_telemetry_logger()
        self._worker_metrics = WorkerMetrics()
        self._storage_metrics = ObjectStorageMetrics()
        self._engine = create_database_engine(settings.database_url.get_secret_value())
        sessions = create_session_factory(self._engine)
        self._repository = SqlAlchemyKnowledgeRepository(sessions)
        self._context_resolver = SqlExecutionContextResolver(sessions)
        self._storage = MinioObjectStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key.get_secret_value(),
            secret_key=settings.minio_secret_key.get_secret_value(),
            bucket=settings.minio_bucket,
            metrics=self._storage_metrics,
            event_logger=configure_storage_telemetry_logger(),
        )
        self._parser = UnstructuredDocumentParser()
        lm_studio = LMStudioAdapter()
        llm_adapters: dict[str, LLMAdapter] = {"lm_studio": lm_studio}
        embedding_adapters: dict[str, EmbeddingAdapter] = {"lm_studio": lm_studio}
        if settings.credential_encryption_key is not None:
            secrets = SqlEncryptedAISecretStore(
                sessions,
                FernetCredentialCipher(settings.credential_encryption_key.get_secret_value()),
            )
            openai = OpenAICompatibleAdapter(secrets)
            llm_adapters["openai"] = openai
            embedding_adapters["openai"] = openai
        ai_bank = AIBank(SqlAIProfileRepository(sessions), llm_adapters, embedding_adapters)
        self._indexer = PgVectorKnowledgeIndexer(self._repository, ai_bank)
        self._envelope_signer = WorkEnvelopeSigner(
            settings.work_envelope_signing_key.get_secret_value()
        )

    async def run(self) -> None:
        """Declare the queue and consume until the process is stopped."""
        connection = await aio_pika.connect_robust(self._settings.rabbitmq_url.get_secret_value())
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=1)
            queue = await declare_ingestion_topology(
                channel,
                self._settings.ingestion_queue_name,
                self._settings.ingestion_dead_letter_queue_name,
            )
            async with queue.iterator() as iterator:
                async for message in iterator:
                    await self._handle(channel, message)

    async def _handle(
        self,
        channel: aio_pika.abc.AbstractChannel,
        message: aio_pika.abc.AbstractIncomingMessage,
    ) -> None:
        raw_retry = message.headers.get("x-tactiqo-retry", 0) if message.headers else 0
        retries = int(raw_retry) if isinstance(raw_retry, (int, str)) else 0
        started = time.perf_counter()
        queue_age_ms = _queue_age_ms(getattr(message, "timestamp", None))
        outcome = "failed"
        correlation_id = "unavailable"
        try:
            payload = json.loads(message.body)
            document_id = UUID(payload["document_id"])
            delegated = self._envelope_signer.verify(payload["work_envelope"])
            correlation_id = delegated.correlation_id
            context = await self._context_resolver.resolve_delegated(
                delegated.actor_id,
                delegated.organization_id,
                delegated.correlation_id,
                delegated.session_assurance,
            )
            await self._process(document_id, self._require_active_context(context))
            await message.ack()
            outcome = "processed"
        except Exception:  # noqa: BLE001 - worker translates provider failures to retry/DLQ
            if retries < self._settings.ingestion_max_retries:
                headers = dict(message.headers or {})
                headers["x-tactiqo-retry"] = retries + 1
                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=message.body,
                        headers=headers,
                        message_id=message.message_id,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        content_type="application/json",
                        timestamp=getattr(message, "timestamp", None) or datetime.now(UTC),
                    ),
                    routing_key=self._settings.ingestion_queue_name,
                )
                await message.ack()
                outcome = "retry_scheduled"
            else:
                try:
                    payload = json.loads(message.body)
                    await self._repository.mark_failed(
                        UUID(payload["document_id"]),
                        "parser_retry_exhausted",
                    )
                finally:
                    await message.reject(requeue=False)
                    outcome = "dead_letter"
        finally:
            worker_metrics = getattr(self, "_worker_metrics", None)
            if worker_metrics is not None:
                worker_metrics.observe_delivery(
                    outcome,
                    (time.perf_counter() - started) * 1000,
                    queue_age_ms,
                )
            self._logger.info(
                "worker.ingestion.delivery.complete",
                extra={
                    "outcome": outcome,
                    "retry_count": min(max(retries, 0), self._settings.ingestion_max_retries + 1),
                    "duration_ms": (time.perf_counter() - started) * 1000,
                    "queue_age_ms": queue_age_ms,
                    "correlation_id": correlation_id,
                },
            )

    @staticmethod
    def _require_active_context(context: ExecutionContext | None) -> ExecutionContext:
        """Fail closed when membership or tenant authority was revoked after enqueue."""
        if context is None:
            message = "Delegated authority is no longer active."
            raise PermissionError(message)
        return context

    async def _process(self, document_id: UUID, context: ExecutionContext) -> None:
        document = await self._repository.get_document(document_id, context)
        if document is None:
            return
        await self._repository.mark_processing(document_id)
        content = await self._storage.get(document.storage_key)
        elements = await self._parser.parse(
            document.id,
            document.name,
            document.content_type,
            content,
        )
        if not elements:
            msg = "Parser produced no usable elements."
            raise ValueError(msg)
        await self._repository.mark_ready(
            document.id,
            self._parser.name,
            self._parser.version,
            elements,
            context,
        )
        ready_document = await self._repository.get_document(document.id)
        if ready_document is not None:
            try:
                await self._indexer.index(ready_document, elements, context)
            except Exception:  # noqa: BLE001 - derived index cannot invalidate canonical truth
                await self._repository.mark_index_degraded(
                    document.id,
                    "derived_index_unavailable",
                )

    async def close(self) -> None:
        """Dispose worker-owned database resources."""
        await self._engine.dispose()


async def async_main() -> None:
    """Run the worker and dispose its database pool on shutdown."""
    settings = Settings()
    worker = IngestionWorker(settings)
    scrape_token = settings.effective_metrics_auth_token
    try:
        if scrape_token is None:
            await worker.run()
            return
        metrics_app = create_worker_metrics_app(
            worker._worker_metrics,  # noqa: SLF001 - composition owns these instances
            worker._storage_metrics,  # noqa: SLF001 - composition owns these instances
            scrape_token.get_secret_value(),
        )
        server = uvicorn.Server(
            uvicorn.Config(
                metrics_app,
                host="0.0.0.0",  # noqa: S104 - container-only; no host port is published
                port=settings.metrics_port,
                access_log=False,
                log_config=None,
            )
        )
        worker_task = asyncio.create_task(worker.run(), name="tactiqo-ingestion-consumer")
        metrics_task = asyncio.create_task(server.serve(), name="tactiqo-worker-metrics")
        try:
            done, _pending = await asyncio.wait(
                {worker_task, metrics_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                task.result()
        finally:
            server.should_exit = True
            for task in (worker_task, metrics_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(worker_task, metrics_task, return_exceptions=True)
    finally:
        await worker.close()


def _queue_age_ms(timestamp: datetime | None) -> float | None:
    """Return bounded age for a broker timestamp; absent legacy timestamps stay unknown."""
    if not isinstance(timestamp, datetime):
        return None
    enqueued_at = timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp
    age_ms = (datetime.now(UTC) - enqueued_at.astimezone(UTC)).total_seconds() * 1000
    if age_ms < 0:
        return 0.0
    return round(min(age_ms, 86_400_000), 3)


if __name__ == "__main__":
    asyncio.run(async_main())
