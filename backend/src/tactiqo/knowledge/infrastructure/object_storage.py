"""MinIO object-storage adapter for original document bytes."""

from io import BytesIO
from logging import Logger
from time import monotonic

import anyio
from minio import Minio

from tactiqo.knowledge.application.telemetry import ObjectStorageMetrics


class MinioObjectStorage:
    """Store originals in one private bucket using the S3-compatible API."""

    def __init__(  # noqa: PLR0913 - explicit metrics and log sinks remain optional
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        metrics: ObjectStorageMetrics | None = None,
        event_logger: Logger | None = None,
    ) -> None:
        """Configure a private S3-compatible object bucket."""
        secure = endpoint.startswith("https://")
        host = endpoint.removeprefix("https://").removeprefix("http://")
        self._client = Minio(host, access_key=access_key, secret_key=secret_key, secure=secure)
        self._bucket = bucket
        self._metrics = metrics
        self._event_logger = event_logger

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        """Create the bucket if needed and upload bytes idempotently."""
        started = monotonic()
        outcome = "failure"
        try:
            await anyio.to_thread.run_sync(self._ensure_bucket)
            await anyio.to_thread.run_sync(
                lambda: self._client.put_object(
                    self._bucket,
                    key,
                    BytesIO(content),
                    len(content),
                    content_type=content_type,
                )
            )
            outcome = "success"
        finally:
            self._record_operation("put", outcome, started)

    async def get(self, key: str) -> bytes:
        """Read and close one object response safely."""

        def _read() -> bytes:
            response = self._client.get_object(self._bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        started = monotonic()
        outcome = "failure"
        try:
            content = await anyio.to_thread.run_sync(_read)
            outcome = "success"
            return content
        finally:
            self._record_operation("get", outcome, started)

    async def delete(self, key: str) -> None:
        """Delete one exact object; MinIO removal is idempotent."""
        started = monotonic()
        outcome = "failure"
        try:
            await anyio.to_thread.run_sync(lambda: self._client.remove_object(self._bucket, key))
            outcome = "success"
        finally:
            self._record_operation("delete", outcome, started)

    def _record_operation(self, operation: str, outcome: str, started: float) -> None:
        """Emit only bounded timings to the explicitly injected observability sinks."""
        duration_ms = (monotonic() - started) * 1000
        if self._metrics is not None:
            self._metrics.observe(operation, outcome, duration_ms)
        if self._event_logger is not None:
            self._event_logger.info(
                "worker.storage.operation.complete",
                extra={
                    "operation": operation,
                    "outcome": outcome,
                    "duration_ms": duration_ms,
                },
            )

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
