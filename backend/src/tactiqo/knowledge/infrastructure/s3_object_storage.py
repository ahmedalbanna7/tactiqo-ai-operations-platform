"""Amazon S3 adapter for canonical document objects."""

from logging import Logger
from time import monotonic

import anyio
import boto3
from botocore.config import Config

from tactiqo.knowledge.application.telemetry import ObjectStorageMetrics


class S3ObjectStorage:
    """Store objects in an infrastructure-managed bucket using the task role."""

    def __init__(
        self,
        region: str,
        bucket: str,
        metrics: ObjectStorageMetrics | None = None,
        event_logger: Logger | None = None,
    ) -> None:
        """Configure a reusable S3 client without static credentials."""
        self._client = boto3.client(
            "s3",
            region_name=region,
            config=Config(
                retries={"max_attempts": 4, "mode": "adaptive"},
                connect_timeout=5,
                read_timeout=60,
                max_pool_connections=32,
            ),
        )
        self._bucket = bucket
        self._metrics = metrics
        self._event_logger = event_logger

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        """Upload an object with the supplied content type."""
        started = monotonic()
        outcome = "failure"
        try:
            await anyio.to_thread.run_sync(
                lambda: self._client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=content,
                    ContentType=content_type,
                )
            )
            outcome = "success"
        finally:
            self._record_operation("put", outcome, started)

    async def get(self, key: str) -> bytes:
        """Download one object and close its streaming body."""
        started = monotonic()
        outcome = "failure"

        def read() -> bytes:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            try:
                return response["Body"].read()
            finally:
                response["Body"].close()

        try:
            content = await anyio.to_thread.run_sync(read)
            outcome = "success"
            return content
        finally:
            self._record_operation("get", outcome, started)

    async def delete(self, key: str) -> None:
        """Delete one object idempotently."""
        started = monotonic()
        outcome = "failure"
        try:
            await anyio.to_thread.run_sync(
                lambda: self._client.delete_object(Bucket=self._bucket, Key=key)
            )
            outcome = "success"
        finally:
            self._record_operation("delete", outcome, started)

    def _record_operation(self, operation: str, outcome: str, started: float) -> None:
        """Record bounded timings without object keys or content."""
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
