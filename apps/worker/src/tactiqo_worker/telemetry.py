"""Sanitized operational event logging for the background worker."""

import hmac
import json
import logging
import math
from contextlib import suppress
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from tactiqo.knowledge.application.telemetry import ObjectStorageMetrics

_OUTCOMES = frozenset({"processed", "retry_scheduled", "dead_letter", "failed"})
_HISTOGRAM_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class WorkerMetrics:
    """Bounded delivery outcome, duration and queue-age metrics for one worker process."""

    def __init__(self) -> None:
        """Initialize fixed-label, process-local worker counters and histograms."""
        self._lock = Lock()
        self._deliveries: dict[str, tuple[int, float, tuple[int, ...]]] = {}
        self._queue_ages: dict[str, tuple[int, float, tuple[int, ...]]] = {}

    def observe_delivery(
        self,
        outcome: str,
        duration_ms: float,
        queue_age_ms: float | None,
    ) -> None:
        """Record a fixed outcome and finite timings without message-derived labels."""
        safe_outcome = outcome if outcome in _OUTCOMES else "failed"
        duration_seconds = _finite_seconds(duration_ms)
        with self._lock:
            self._deliveries[safe_outcome] = _observe_histogram(
                self._deliveries.get(safe_outcome), duration_seconds
            )
            if queue_age_ms is not None:
                queue_age_seconds = _finite_seconds(queue_age_ms)
                self._queue_ages[safe_outcome] = _observe_histogram(
                    self._queue_ages.get(safe_outcome), queue_age_seconds
                )

    def render_prometheus(self) -> str:
        """Render worker delivery and queue-age metrics with bounded outcome labels."""
        lines = [
            "# TYPE tactiqo_worker_deliveries_total counter",
            "# TYPE tactiqo_worker_delivery_duration_seconds histogram",
            "# TYPE tactiqo_worker_delivery_queue_age_seconds histogram",
        ]
        with self._lock:
            deliveries = tuple(sorted(self._deliveries.items()))
            queue_ages = tuple(sorted(self._queue_ages.items()))
        for outcome, sample in deliveries:
            lines.extend(
                _render_histogram(
                    "tactiqo_worker_delivery_duration_seconds", sample, outcome
                )
            )
            lines.append(f'tactiqo_worker_deliveries_total{{outcome="{outcome}"}} {sample[0]}')
        for outcome, sample in queue_ages:
            lines.extend(
                _render_histogram(
                    "tactiqo_worker_delivery_queue_age_seconds", sample, outcome
                )
            )
        return "\n".join(lines) + "\n"


def create_worker_metrics_app(
    worker_metrics: WorkerMetrics,
    storage_metrics: ObjectStorageMetrics,
    token: str,
) -> FastAPI:
    """Create a private bearer-protected metrics surface; never bind it to the host."""
    if not token.strip():
        message = "Worker metrics require a non-empty scrape token."
        raise ValueError(message)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/internal/metrics", include_in_schema=False)
    async def internal_metrics(request: Request) -> PlainTextResponse:
        """Expose only bounded worker and storage metric families after bearer auth."""
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {token}"
        if not hmac.compare_digest(
            supplied.encode("utf-8", errors="replace"), expected.encode("utf-8")
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
        return PlainTextResponse(
            worker_metrics.render_prometheus() + storage_metrics.render_prometheus(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app


def _finite_seconds(duration_ms: float) -> float:
    """Normalize a duration to finite, non-negative seconds."""
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, (int, float)):
        return 0.0
    if not math.isfinite(duration_ms):
        return 0.0
    return min(max(float(duration_ms) / 1000, 0.0), 86_400.0)


def _observe_histogram(
    current: tuple[int, float, tuple[int, ...]] | None,
    value: float,
) -> tuple[int, float, tuple[int, ...]]:
    """Update one fixed-bucket histogram sample."""
    count, total, buckets = current or (0, 0.0, (0,) * len(_HISTOGRAM_BUCKETS))
    updated_buckets = tuple(
        bucket_count + int(value <= upper_bound)
        for bucket_count, upper_bound in zip(buckets, _HISTOGRAM_BUCKETS, strict=True)
    )
    return count + 1, total + value, updated_buckets


def _render_histogram(
    name: str,
    sample: tuple[int, float, tuple[int, ...]],
    outcome: str,
) -> list[str]:
    """Render a Prometheus histogram using the single bounded outcome label."""
    count, total, buckets = sample
    labels = f'outcome="{outcome}"'
    lines = []
    for bucket_count, upper_bound in zip(buckets, _HISTOGRAM_BUCKETS, strict=True):
        lines.append(
            f'{name}_bucket{{{labels},le="{upper_bound:g}"}} {bucket_count}'
        )
    lines.extend(
        (
            f'{name}_bucket{{{labels},le="+Inf"}} {count}',
            f"{name}_sum{{{labels}}} {total:.9g}",
            f"{name}_count{{{labels}}} {count}",
        )
    )
    return lines

class WorkerEventFormatter(logging.Formatter):
    """Render only the fixed ingestion-delivery telemetry contract."""

    def format(self, record: logging.LogRecord) -> str:
        """Discard arbitrary message text and serialize bounded safe fields only."""
        outcome = getattr(record, "outcome", "unknown")
        if outcome not in {"processed", "retry_scheduled", "dead_letter", "failed"}:
            outcome = "unknown"
        retry_count = getattr(record, "retry_count", 0)
        if not isinstance(retry_count, int):
            retry_count = 0
        duration_ms = getattr(record, "duration_ms", 0.0)
        if not isinstance(duration_ms, (int, float)) or not math.isfinite(duration_ms):
            duration_ms = 0.0
        queue_age_ms = getattr(record, "queue_age_ms", None)
        if (
            isinstance(queue_age_ms, bool)
            or not isinstance(queue_age_ms, (int, float))
            or not math.isfinite(queue_age_ms)
        ):
            queue_age_ms = None
        else:
            queue_age_ms = round(max(min(float(queue_age_ms), 86_400_000), 0.0), 3)
        raw_correlation_id = getattr(record, "correlation_id", None)
        correlation_id = "unavailable"
        if isinstance(raw_correlation_id, str):
            with suppress(ValueError):
                correlation_id = str(UUID(raw_correlation_id))
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "event": "worker.ingestion.delivery.complete",
            "component": "ingestion_worker",
            "operation": "document_ingestion",
            "correlation_id": correlation_id,
            "outcome": outcome,
            "retry_count": max(0, min(retry_count, 100)),
            "duration_ms": round(max(float(duration_ms), 0.0), 3),
            "queue_age_ms": queue_age_ms,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class StorageEventFormatter(logging.Formatter):
    """Render only allowlisted storage operation telemetry from the ingestion worker."""

    def format(self, record: logging.LogRecord) -> str:
        """Discard messages, object metadata and every non-contract record attribute."""
        operation = getattr(record, "operation", None)
        if not isinstance(operation, str) or operation not in {"put", "get", "delete"}:
            operation = "unknown"
        outcome = getattr(record, "outcome", None)
        if not isinstance(outcome, str) or outcome not in {"success", "failure"}:
            outcome = "unknown"
        duration_ms = getattr(record, "duration_ms", 0.0)
        if not isinstance(duration_ms, (int, float)) or not math.isfinite(duration_ms):
            duration_ms = 0.0
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "event": "worker.storage.operation.complete",
            "component": "ingestion_worker",
            "operation": operation,
            "outcome": outcome,
            "duration_ms": round(max(float(duration_ms), 0.0), 3),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_worker_telemetry_logger() -> logging.Logger:
    """Configure the isolated, allowlisted JSON event logger for this process."""
    logger = logging.getLogger("tactiqo.worker")
    if not getattr(logger, "handlers", None):
        handler = logging.StreamHandler()
        handler.setFormatter(WorkerEventFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def configure_storage_telemetry_logger() -> logging.Logger:
    """Configure a separate allowlisted JSON logger for worker-owned storage operations."""
    logger = logging.getLogger("tactiqo.worker.storage")
    if not getattr(logger, "handlers", None):
        handler = logging.StreamHandler()
        handler.setFormatter(StorageEventFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
