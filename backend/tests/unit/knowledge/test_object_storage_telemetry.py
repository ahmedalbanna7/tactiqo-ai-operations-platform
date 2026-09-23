"""Object-storage metrics are fixed-label and never include object metadata."""

import asyncio
import io
import json
import logging

import pytest

import tactiqo.knowledge.infrastructure.object_storage as storage_module
from tactiqo.knowledge.application.telemetry import ObjectStorageMetrics
from tactiqo.knowledge.infrastructure.object_storage import MinioObjectStorage
from tactiqo_worker.telemetry import StorageEventFormatter


class FakeObjectResponse:
    """MinIO response stub that tracks resource cleanup."""

    def __init__(self, content: bytes) -> None:
        """Store response bytes."""
        self._content = content
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        """Return the fake object payload."""
        return self._content

    def close(self) -> None:
        """Record response close."""
        self.closed = True

    def release_conn(self) -> None:
        """Record connection release."""
        self.released = True


class FakeMinio:
    """In-memory client with the small MinIO surface used by the adapter."""

    def __init__(self) -> None:
        """Initialize one fake object and operation state."""
        self.content = b"sensitive document bytes"
        self.fail_put = False
        self.response: FakeObjectResponse | None = None

    def bucket_exists(self, _bucket: str) -> bool:
        """Report an existing test bucket."""
        return True

    def make_bucket(self, _bucket: str) -> None:
        """Satisfy the adapter's optional bucket initialization."""

    def put_object(
        self,
        _bucket: str,
        _key: str,
        _data: object,
        _length: int,
        *,
        content_type: str,
    ) -> None:
        """Succeed or simulate a provider failure without retaining the stream."""
        if self.fail_put:
            error_message = "private storage failure detail"
            raise RuntimeError(error_message)
        assert content_type == "application/pdf"

    def get_object(self, _bucket: str, _key: str) -> FakeObjectResponse:
        """Return a response that can be verified for cleanup."""
        self.response = FakeObjectResponse(self.content)
        return self.response

    def remove_object(self, _bucket: str, _key: str) -> None:
        """Complete a fake idempotent removal."""


def test_storage_operations_preserve_results_and_redact_object_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Put/get/delete metrics contain only fixed operation and outcome labels."""
    client = FakeMinio()
    monkeypatch.setattr(storage_module, "Minio", lambda *_args, **_kwargs: client)
    metrics = ObjectStorageMetrics()
    log_stream = io.StringIO()
    logger = logging.Logger("test.worker.storage")  # noqa: LOG001 - isolated event capture
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(StorageEventFormatter())
    logger.addHandler(handler)
    storage = MinioObjectStorage(
        "https://private-storage.example",
        "access-secret",
        "secret-key",
        "private-bucket",
        metrics,
        logger,
    )

    asyncio.run(storage.put("tenant-secret/document-secret.pdf", b"bytes", "application/pdf"))
    result = asyncio.run(storage.get("tenant-secret/document-secret.pdf"))
    asyncio.run(storage.delete("tenant-secret/document-secret.pdf"))

    rendered = metrics.render_prometheus()
    assert result == client.content
    assert client.response is not None
    assert client.response.closed
    assert client.response.released
    events = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    assert [event["operation"] for event in events] == ["put", "get", "delete"]
    assert all(event["outcome"] == "success" for event in events)
    for operation in ("put", "get", "delete"):
        assert (
            f'tactiqo_object_storage_operations_total{{operation="{operation}",'
            'outcome="success"} 1'
        ) in rendered
    for secret in (
        "tenant-secret",
        "document-secret",
        "private-bucket",
        "private-storage.example",
        "access-secret",
        "sensitive document bytes",
        "application/pdf",
    ):
        assert secret not in rendered
        assert secret not in log_stream.getvalue()


def test_storage_failure_is_counted_without_exposing_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MinIO errors propagate while metrics keep only failure outcome and operation."""
    client = FakeMinio()
    client.fail_put = True
    monkeypatch.setattr(storage_module, "Minio", lambda *_args, **_kwargs: client)
    metrics = ObjectStorageMetrics()
    storage = MinioObjectStorage(
        "http://storage",
        "access",
        "secret",
        "bucket",
        metrics,
    )

    with pytest.raises(RuntimeError, match="private storage failure detail"):
        asyncio.run(storage.put("private-key", b"content", "application/pdf"))

    rendered = metrics.render_prometheus()
    assert (
        'tactiqo_object_storage_operations_total{operation="put",outcome="failure"} 1'
        in rendered
    )
    assert "private storage failure detail" not in rendered
    assert "private-key" not in rendered
