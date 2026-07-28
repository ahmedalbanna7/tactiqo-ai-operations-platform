"""RabbitMQ consumer for isolated document parsing and indexing."""

import asyncio
import json
from uuid import UUID

import aio_pika

from tactiqo.ingestion.infrastructure.unstructured_parser import UnstructuredDocumentParser
from tactiqo.integrations.onyx.adapter import OnyxAdapter
from tactiqo.knowledge.application.ports import KnowledgeIndexer
from tactiqo.knowledge.infrastructure.indexer import DisabledKnowledgeIndexer
from tactiqo.knowledge.infrastructure.object_storage import MinioObjectStorage
from tactiqo.knowledge.infrastructure.queue import declare_ingestion_topology
from tactiqo.knowledge.infrastructure.repositories import SqlAlchemyKnowledgeRepository
from tactiqo.shared.infrastructure.database import create_database_engine, create_session_factory
from tactiqo.shared.infrastructure.settings import Settings


class IngestionWorker:
    """Process one document per delivery with bounded retry and safe failure codes."""

    def __init__(self, settings: Settings) -> None:
        """Compose worker-owned adapters from validated settings."""
        self._settings = settings
        self._engine = create_database_engine(settings.database_url.get_secret_value())
        self._repository = SqlAlchemyKnowledgeRepository(create_session_factory(self._engine))
        self._storage = MinioObjectStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key.get_secret_value(),
            secret_key=settings.minio_secret_key.get_secret_value(),
            bucket=settings.minio_bucket,
        )
        self._parser = UnstructuredDocumentParser()
        self._indexer: KnowledgeIndexer = self._build_indexer(settings)

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
        try:
            payload = json.loads(message.body)
            document_id = UUID(payload["document_id"])
            await self._process(document_id)
            await message.ack()
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
                    ),
                    routing_key=self._settings.ingestion_queue_name,
                )
                await message.ack()
            else:
                try:
                    payload = json.loads(message.body)
                    await self._repository.mark_failed(
                        UUID(payload["document_id"]),
                        "parser_retry_exhausted",
                    )
                finally:
                    await message.reject(requeue=False)

    async def _process(self, document_id: UUID) -> None:
        document = await self._repository.get_document(document_id)
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
        )
        ready_document = await self._repository.get_document(document.id)
        if ready_document is not None:
            try:
                await self._indexer.index(ready_document, elements)
            except Exception:  # noqa: BLE001 - derived index cannot invalidate canonical truth
                await self._repository.mark_index_degraded(
                    document.id,
                    "derived_index_unavailable",
                )

    def _build_indexer(self, settings: Settings) -> KnowledgeIndexer:
        if not settings.knowledge_search_enabled or settings.onyx_service_token is None:
            return DisabledKnowledgeIndexer()
        return OnyxAdapter(
            base_url=settings.onyx_base_url,
            token=settings.onyx_service_token.get_secret_value(),
            repository=self._repository,
        )

    async def close(self) -> None:
        """Dispose worker-owned database resources."""
        await self._engine.dispose()


async def async_main() -> None:
    """Run the worker and dispose its database pool on shutdown."""
    worker = IngestionWorker(Settings())
    try:
        await worker.run()
    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(async_main())
