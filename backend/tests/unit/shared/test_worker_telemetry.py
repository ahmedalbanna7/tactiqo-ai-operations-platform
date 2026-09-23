"""Worker operational telemetry is bounded and contains no message-derived values."""

import asyncio
import io
import json
import logging
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx

from tactiqo.knowledge.application.telemetry import ObjectStorageMetrics
from tactiqo_worker.main import IngestionWorker
from tactiqo_worker.telemetry import (
    StorageEventFormatter,
    WorkerEventFormatter,
    WorkerMetrics,
    create_worker_metrics_app,
)

LOG_RECORD_LINE = 20
UNBOUNDED_RETRY_COUNT = 10_000
MAX_LOGGED_RETRY_COUNT = 100
EXPECTED_ROUNDED_DURATION_MS = 12.346
EXPECTED_STORAGE_DURATION_MS = 18.123
MIN_EXPECTED_QUEUE_AGE_MS = 2_000
MAX_EXPECTED_QUEUE_AGE_MS = 10_000


def test_worker_event_formatter_discards_payload_and_bounds_retry_fields() -> None:
    """Only the fixed worker event contract can reach the JSON log line."""
    record = logging.LogRecord(
        "tactiqo.worker",
        logging.INFO,
        "main.py",
        LOG_RECORD_LINE,
        "failed to process document document-secret Bearer provider-secret",
        (),
        None,
    )
    record.outcome = "retry_scheduled"
    record.correlation_id = "c8e88d2f-80dc-49fb-aa8e-f390d9501009"
    record.retry_count = UNBOUNDED_RETRY_COUNT
    record.duration_ms = 12.34567
    record.document_id = "document-secret"
    record.authorization = "Bearer provider-secret"

    rendered = WorkerEventFormatter().format(record)
    event = json.loads(rendered)

    assert event["event"] == "worker.ingestion.delivery.complete"
    assert event["component"] == "ingestion_worker"
    assert event["operation"] == "document_ingestion"
    assert event["outcome"] == "retry_scheduled"
    assert event["correlation_id"] == "c8e88d2f-80dc-49fb-aa8e-f390d9501009"
    assert event["retry_count"] == MAX_LOGGED_RETRY_COUNT
    assert event["duration_ms"] == EXPECTED_ROUNDED_DURATION_MS
    assert event["queue_age_ms"] is None
    assert "document-secret" not in rendered
    assert "provider-secret" not in rendered


def test_worker_formatter_collapses_unknown_outcome_and_invalid_duration() -> None:
    """Unexpected metric fields cannot add unbounded labels or arbitrary log text."""
    record = logging.LogRecord(
        "tactiqo.worker",
        logging.INFO,
        "main.py",
        LOG_RECORD_LINE,
        "unexpected raw error text",
        (),
        None,
    )
    record.outcome = "tenant-specific-error"
    record.correlation_id = "tenant-secret-not-a-uuid"
    record.retry_count = "many"
    record.duration_ms = float("nan")

    rendered = WorkerEventFormatter().format(record)
    event = json.loads(rendered)

    assert event["outcome"] == "unknown"
    assert event["correlation_id"] == "unavailable"
    assert event["retry_count"] == 0
    assert event["duration_ms"] == 0.0
    assert event["queue_age_ms"] is None
    assert "unexpected raw error text" not in rendered
    assert "tenant-specific-error" not in rendered


def test_storage_event_formatter_discards_message_and_object_metadata() -> None:
    """Worker storage events retain only the fixed operation/outcome/time contract."""
    record = logging.LogRecord(
        "tactiqo.worker.storage",
        logging.INFO,
        "object_storage.py",
        LOG_RECORD_LINE,
        "failed bucket=private-bucket key=tenant-secret/object.pdf",
        (),
        None,
    )
    record.operation = "get"
    record.outcome = "failure"
    record.duration_ms = 18.12345
    record.object_key = "tenant-secret/object.pdf"

    rendered = StorageEventFormatter().format(record)
    event = json.loads(rendered)

    assert event["event"] == "worker.storage.operation.complete"
    assert event["component"] == "ingestion_worker"
    assert event["operation"] == "get"
    assert event["outcome"] == "failure"
    assert event["duration_ms"] == EXPECTED_STORAGE_DURATION_MS
    assert "private-bucket" not in rendered
    assert "tenant-secret" not in rendered


def test_successful_delivery_emits_processed_without_document_identifier() -> None:
    """A real worker success path logs only safe outcome metadata."""
    stream = io.StringIO()
    logger = logging.Logger("test.tactiqo.worker")  # noqa: LOG001 - isolated handler for test capture
    handler = logging.StreamHandler(stream)
    handler.setFormatter(WorkerEventFormatter())
    logger.addHandler(handler)
    worker = IngestionWorker.__new__(IngestionWorker)
    worker._settings = SimpleNamespace(ingestion_max_retries=3)  # noqa: SLF001
    worker._logger = logger  # noqa: SLF001
    worker._envelope_signer = SimpleNamespace(  # noqa: SLF001
        verify=lambda _envelope: SimpleNamespace(
            actor_id=uuid4(),
            organization_id=uuid4(),
            correlation_id="c8e88d2f-80dc-49fb-aa8e-f390d9501009",
            session_assurance="authenticated",
        )
    )
    context = object()
    worker._context_resolver = SimpleNamespace(  # noqa: SLF001
        resolve_delegated=AsyncMock(return_value=context)
    )
    worker._process = AsyncMock()  # noqa: SLF001
    document_id = uuid4()
    message = SimpleNamespace(
        headers={},
        body=json.dumps({"document_id": str(document_id), "work_envelope": "opaque"}).encode(),
        message_id="internal-message-id",
        ack=AsyncMock(),
    )

    asyncio.run(worker._handle(SimpleNamespace(), message))  # noqa: SLF001

    message.ack.assert_awaited_once()
    worker._process.assert_awaited_once_with(document_id, context)  # noqa: SLF001
    event = json.loads(stream.getvalue())
    assert event["outcome"] == "processed"
    assert event["correlation_id"] == "c8e88d2f-80dc-49fb-aa8e-f390d9501009"
    assert event["retry_count"] == 0
    assert event["queue_age_ms"] is None
    assert str(document_id) not in stream.getvalue()
    assert "internal-message-id" not in stream.getvalue()


def test_retry_delivery_emits_retry_scheduled_without_message_body() -> None:
    """An invalid envelope follows existing retry behavior and emits only safe metadata."""
    stream = io.StringIO()
    logger = logging.Logger("test.tactiqo.worker.retry")  # noqa: LOG001 - isolated capture
    handler = logging.StreamHandler(stream)
    handler.setFormatter(WorkerEventFormatter())
    logger.addHandler(handler)
    worker = IngestionWorker.__new__(IngestionWorker)
    worker._settings = SimpleNamespace(  # noqa: SLF001
        ingestion_max_retries=2,
        ingestion_queue_name="ingestion.queue",
    )
    worker._logger = logger  # noqa: SLF001

    def invalid_envelope(_envelope: str) -> None:
        """Simulate signature validation failure without exposing details."""
        failure_reason = "tenant secret invalid signature"
        raise ValueError(failure_reason)

    worker._envelope_signer = SimpleNamespace(verify=invalid_envelope)  # noqa: SLF001
    channel = SimpleNamespace(default_exchange=SimpleNamespace(publish=AsyncMock()))
    enqueued_at = datetime.now(UTC) - timedelta(seconds=3)
    document_id = uuid4()
    message = SimpleNamespace(
        headers={},
        body=json.dumps({"document_id": str(document_id), "work_envelope": "invalid"}).encode(),
        message_id="message-secret-id",
        timestamp=enqueued_at,
        ack=AsyncMock(),
    )

    asyncio.run(worker._handle(channel, message))  # noqa: SLF001

    message.ack.assert_awaited_once()
    channel.default_exchange.publish.assert_awaited_once()
    retried_message = channel.default_exchange.publish.await_args.args[0]
    assert retried_message.timestamp == enqueued_at
    event = json.loads(stream.getvalue())
    assert event["outcome"] == "retry_scheduled"
    assert MIN_EXPECTED_QUEUE_AGE_MS <= event["queue_age_ms"] <= MAX_EXPECTED_QUEUE_AGE_MS
    assert event["correlation_id"] == "unavailable"
    assert str(document_id) not in stream.getvalue()
    assert "message-secret-id" not in stream.getvalue()
    assert "tenant secret invalid signature" not in stream.getvalue()


def test_exhausted_delivery_emits_dead_letter_without_document_id() -> None:
    """Exhausted processing is logged as DLQ without canonical identifiers."""
    stream = io.StringIO()
    logger = logging.Logger("test.tactiqo.worker.dlq")  # noqa: LOG001 - isolated capture
    handler = logging.StreamHandler(stream)
    handler.setFormatter(WorkerEventFormatter())
    logger.addHandler(handler)
    worker = IngestionWorker.__new__(IngestionWorker)
    worker._settings = SimpleNamespace(ingestion_max_retries=0)  # noqa: SLF001
    worker._logger = logger  # noqa: SLF001

    def invalid_envelope(_envelope: str) -> None:
        """Simulate a permanently invalid delegated envelope."""
        failure_reason = "invalid signature"
        raise ValueError(failure_reason)

    worker._envelope_signer = SimpleNamespace(verify=invalid_envelope)  # noqa: SLF001
    worker._repository = SimpleNamespace(mark_failed=AsyncMock())  # noqa: SLF001
    document_id = uuid4()
    message = SimpleNamespace(
        headers={"x-tactiqo-retry": 0},
        body=json.dumps({"document_id": str(document_id), "work_envelope": "invalid"}).encode(),
        message_id="message-secret-id",
        reject=AsyncMock(),
    )

    asyncio.run(worker._handle(SimpleNamespace(), message))  # noqa: SLF001

    message.reject.assert_awaited_once_with(requeue=False)
    worker._repository.mark_failed.assert_awaited_once_with(  # noqa: SLF001
        document_id, "parser_retry_exhausted"
    )
    event = json.loads(stream.getvalue())
    assert event["outcome"] == "dead_letter"
    assert event["queue_age_ms"] is None
    assert str(document_id) not in stream.getvalue()
    assert "message-secret-id" not in stream.getvalue()


def test_worker_metrics_use_only_fixed_outcomes_and_bounded_timings() -> None:
    """Delivery and queue-age metrics contain no message-derived labels."""
    metrics = WorkerMetrics()
    metrics.observe_delivery("processed", 12.5, 2_500)
    metrics.observe_delivery("organization-secret", float("nan"), None)

    rendered = metrics.render_prometheus()

    assert 'tactiqo_worker_deliveries_total{outcome="processed"} 1' in rendered
    assert 'tactiqo_worker_deliveries_total{outcome="failed"} 1' in rendered
    assert 'tactiqo_worker_delivery_duration_seconds_count{outcome="processed"} 1' in rendered
    assert 'tactiqo_worker_delivery_queue_age_seconds_count{outcome="processed"} 1' in rendered
    assert "organization-secret" not in rendered


def test_worker_metrics_endpoint_requires_bearer_token_and_scrapes_safe_families() -> None:
    """The internal scrape endpoint denies unauthenticated reads and excludes secrets."""
    token = "private-worker-scrape-token"  # noqa: S105 - test-only bearer credential
    worker_metrics = WorkerMetrics()
    worker_metrics.observe_delivery("processed", 9.5, 800)
    storage_metrics = ObjectStorageMetrics()
    storage_metrics.observe("get", "success", 5)
    app = create_worker_metrics_app(worker_metrics, storage_metrics, token)

    async def _scrape() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.get("/internal/metrics")
            allowed = await client.get(
                "/internal/metrics",
                headers={"Authorization": f"Bearer {token}"},
            )
            return denied, allowed

    denied, allowed = asyncio.run(_scrape())

    assert denied.status_code == HTTPStatus.NOT_FOUND
    assert allowed.status_code == HTTPStatus.OK
    assert "tactiqo_worker_deliveries_total" in allowed.text
    assert "tactiqo_worker_delivery_queue_age_seconds" in allowed.text
    assert "tactiqo_object_storage_operations_total" in allowed.text
    assert token not in allowed.text
