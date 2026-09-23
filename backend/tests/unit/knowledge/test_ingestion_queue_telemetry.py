"""Ingestion publishing metrics expose outcomes, never message-derived identifiers."""

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import tactiqo.knowledge.infrastructure.queue as queue_module
from tactiqo.knowledge.application.telemetry import IngestionQueueMetrics
from tactiqo.knowledge.infrastructure.queue import RabbitMqIngestionPublisher
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.work_envelope import WorkEnvelopeSigner

MAX_EXPECTED_QUEUE_READY_MESSAGES = 2_147_483_647


class FakeConnection:
    """Async context-managed connection for publisher tests."""

    def __init__(self, channel: SimpleNamespace) -> None:
        """Store a fake channel."""
        self._channel = channel

    async def __aenter__(self) -> "FakeConnection":
        """Enter the fake connection context."""
        return self

    async def __aexit__(self, *_args: object) -> None:
        """Close the fake connection context."""

    async def channel(self, *, publisher_confirms: bool) -> SimpleNamespace:
        """Return a fake channel while validating confirms are requested."""
        assert publisher_confirms is True
        return self._channel


def _publisher(metrics: IngestionQueueMetrics) -> RabbitMqIngestionPublisher:
    """Build a publisher with local-only test credentials."""
    return RabbitMqIngestionPublisher(
        "amqp://ignored",
        "ingestion.test",
        "ingestion.dead.test",
        WorkEnvelopeSigner("a" * 32),
        metrics,
    )


def _context() -> ExecutionContext:
    """Build the minimum signed context needed by the publisher."""
    return ExecutionContext("actor", "tenant-secret", "correlation", "internal", "test")


def test_successful_publish_records_only_fixed_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    """A confirmed publish records success without the document ID or queue name."""
    exchange = SimpleNamespace(publish=AsyncMock())
    connection = FakeConnection(SimpleNamespace(default_exchange=exchange))
    monkeypatch.setattr(queue_module.aio_pika, "connect_robust", _async_connection(connection))
    queue_snapshot = SimpleNamespace(
        declaration_result=SimpleNamespace(message_count=7),
    )
    monkeypatch.setattr(
        queue_module,
        "declare_ingestion_topology",
        AsyncMock(return_value=queue_snapshot),
    )
    metrics = IngestionQueueMetrics()

    asyncio.run(_publisher(metrics).publish(uuid4(), _context()))

    published_message = exchange.publish.await_args.args[0]
    assert published_message.timestamp is not None
    assert published_message.timestamp.tzinfo == queue_module.UTC
    rendered = metrics.render_prometheus()
    assert 'tactiqo_ingestion_publish_total{outcome="success"} 1' in rendered
    assert "tactiqo_ingestion_queue_ready_messages 7" in rendered
    assert "tactiqo_ingestion_queue_depth_observed_at_seconds " in rendered
    assert "tenant-secret" not in rendered
    assert "ingestion.test" not in rendered


def test_publish_exception_records_failure_and_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Broker errors stay visible to callers but are not copied into metrics."""

    async def fail_connect(_url: str) -> FakeConnection:
        """Simulate an unavailable broker with sensitive detail."""
        error_text = "broker secret detail"
        raise RuntimeError(error_text)

    monkeypatch.setattr(queue_module.aio_pika, "connect_robust", fail_connect)
    metrics = IngestionQueueMetrics()

    with pytest.raises(RuntimeError, match="broker secret detail"):
        asyncio.run(_publisher(metrics).publish(uuid4(), _context()))

    rendered = metrics.render_prometheus()
    assert 'tactiqo_ingestion_publish_total{outcome="failure"} 1' in rendered
    assert "broker secret detail" not in rendered


def test_queue_depth_metric_rejects_invalid_and_bounds_unexpected_counts() -> None:
    """Queue depth is a single bounded gauge with no broker or tenant labels."""
    metrics = IngestionQueueMetrics()
    metrics.observe_queue_depth(4.5)
    assert "\ntactiqo_ingestion_queue_ready_messages " not in metrics.render_prometheus()

    metrics.observe_queue_depth(-12)
    assert "tactiqo_ingestion_queue_ready_messages 0" in metrics.render_prometheus()

    metrics.observe_queue_depth(MAX_EXPECTED_QUEUE_READY_MESSAGES + 1)
    rendered = metrics.render_prometheus()
    assert f"tactiqo_ingestion_queue_ready_messages {MAX_EXPECTED_QUEUE_READY_MESSAGES}" in rendered
    assert "tenant" not in rendered


def _async_connection(
    connection: FakeConnection,
) -> Callable[[str], Awaitable[FakeConnection]]:
    """Build an async connection factory for monkeypatching the Rabbit client."""

    async def connect(_url: str) -> FakeConnection:
        """Return the configured fake connection."""
        return connection

    return connect


async def _async_noop(*_args: object, **_kwargs: object) -> None:
    """Return immediately for mocked async queue operations."""
