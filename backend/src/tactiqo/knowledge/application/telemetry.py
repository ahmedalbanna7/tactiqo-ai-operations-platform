"""Bounded process-local retrieval metrics."""

import math
from threading import Lock
from time import time

_OPERATIONS = frozenset({"search", "list_sources"})
_OUTCOMES = frozenset({"primary", "fallback", "failure"})
_HISTOGRAM_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_QUEUE_OUTCOMES = frozenset({"success", "failure"})
_MAX_QUEUE_READY_MESSAGES = 2_147_483_647
_STORAGE_OPERATIONS = frozenset({"put", "get", "delete"})
_STORAGE_OUTCOMES = frozenset({"success", "failure"})


class RetrievalMetrics:
    """Aggregate retrieval path and latency without search content or tenant labels."""

    def __init__(self) -> None:
        """Initialize an in-memory fixed-cardinality registry."""
        self._lock = Lock()
        self._series: dict[tuple[str, str], tuple[int, float, tuple[int, ...]]] = {}

    def observe(self, operation: str, outcome: str, duration_ms: float) -> None:
        """Record a retrieval operation using fixed operation/outcome dimensions."""
        safe_operation = (
            operation if isinstance(operation, str) and operation in _OPERATIONS else "other"
        )
        safe_outcome = outcome if isinstance(outcome, str) and outcome in _OUTCOMES else "failure"
        try:
            duration_seconds = float(duration_ms) / 1000
        except (OverflowError, TypeError, ValueError):
            duration_seconds = 0.0
        if not math.isfinite(duration_seconds):
            duration_seconds = 0.0
        duration_seconds = max(duration_seconds, 0.0)
        key = (safe_operation, safe_outcome)
        with self._lock:
            count, total, buckets = self._series.get(
                key, (0, 0.0, (0,) * len(_HISTOGRAM_BUCKETS))
            )
            observed_buckets = tuple(
                bucket_count + int(duration_seconds <= upper_bound)
                for bucket_count, upper_bound in zip(
                    buckets, _HISTOGRAM_BUCKETS, strict=True
                )
            )
            self._series[key] = (count + 1, total + duration_seconds, observed_buckets)

    def render_prometheus(self) -> str:
        """Render fixed-cardinality retrieval counters and latency histograms."""
        lines = [
            "# TYPE tactiqo_knowledge_retrieval_total counter",
            "# TYPE tactiqo_knowledge_retrieval_duration_seconds histogram",
        ]
        with self._lock:
            snapshot = tuple(sorted(self._series.items()))
        for (operation, outcome), (count, total, buckets) in snapshot:
            labels = self._labels(operation, outcome)
            lines.append(f"tactiqo_knowledge_retrieval_total{{{labels}}} {count}")
            for bucket_count, upper_bound in zip(
                buckets, _HISTOGRAM_BUCKETS, strict=True
            ):
                bucket_labels = self._labels(operation, outcome, le=f"{upper_bound:g}")
                lines.append(
                    "tactiqo_knowledge_retrieval_duration_seconds_bucket"
                    f"{{{bucket_labels}}} {bucket_count}"
                )
            infinity_labels = self._labels(operation, outcome, le="+Inf")
            lines.extend(
                (
                    "tactiqo_knowledge_retrieval_duration_seconds_bucket"
                    f"{{{infinity_labels}}} {count}",
                    f"tactiqo_knowledge_retrieval_duration_seconds_sum{{{labels}}} {total:.9g}",
                    f"tactiqo_knowledge_retrieval_duration_seconds_count{{{labels}}} {count}",
                )
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _labels(operation: str, outcome: str, *, le: str | None = None) -> str:
        """Build labels from safe fixed values only."""
        labels = [f'operation="{operation}"', f'outcome="{outcome}"']
        if le is not None:
            labels.append(f'le="{le}"')
        return ",".join(labels)


class IngestionQueueMetrics:
    """Aggregate queue publish outcomes without queue, message, or document labels."""

    def __init__(self) -> None:
        """Initialize a process-local bounded registry."""
        self._lock = Lock()
        self._series: dict[str, tuple[int, float, tuple[int, ...]]] = {}
        self._queue_ready_messages: int | None = None
        self._queue_depth_observed_at: float | None = None

    def observe_queue_depth(self, message_count: int) -> None:
        """Store the latest broker-reported ready-message count without dynamic labels."""
        if isinstance(message_count, bool) or not isinstance(message_count, int):
            return
        with self._lock:
            self._queue_ready_messages = min(max(message_count, 0), _MAX_QUEUE_READY_MESSAGES)
            self._queue_depth_observed_at = time()

    def observe(self, outcome: str, duration_ms: float) -> None:
        """Record one ingestion publish attempt using a fixed outcome value."""
        safe_outcome = (
            outcome if isinstance(outcome, str) and outcome in _QUEUE_OUTCOMES else "failure"
        )
        try:
            duration_seconds = float(duration_ms) / 1000
        except (OverflowError, TypeError, ValueError):
            duration_seconds = 0.0
        if not math.isfinite(duration_seconds):
            duration_seconds = 0.0
        duration_seconds = max(duration_seconds, 0.0)
        with self._lock:
            count, total, buckets = self._series.get(
                safe_outcome, (0, 0.0, (0,) * len(_HISTOGRAM_BUCKETS))
            )
            observed_buckets = tuple(
                bucket_count + int(duration_seconds <= upper_bound)
                for bucket_count, upper_bound in zip(
                    buckets, _HISTOGRAM_BUCKETS, strict=True
                )
            )
            self._series[safe_outcome] = (count + 1, total + duration_seconds, observed_buckets)

    def render_prometheus(self) -> str:
        """Render publish counters and latency histograms without dynamic labels."""
        lines = [
            "# TYPE tactiqo_ingestion_publish_total counter",
            "# TYPE tactiqo_ingestion_publish_duration_seconds histogram",
            "# TYPE tactiqo_ingestion_queue_ready_messages gauge",
            "# TYPE tactiqo_ingestion_queue_depth_observed_at_seconds gauge",
        ]
        with self._lock:
            snapshot = tuple(sorted(self._series.items()))
            queue_ready_messages = self._queue_ready_messages
            queue_depth_observed_at = self._queue_depth_observed_at
        if queue_ready_messages is not None and queue_depth_observed_at is not None:
            lines.extend(
                (
                    "tactiqo_ingestion_queue_ready_messages "
                    f"{queue_ready_messages}",
                    "tactiqo_ingestion_queue_depth_observed_at_seconds "
                    f"{queue_depth_observed_at:.3f}",
                )
            )
        for outcome, (count, total, buckets) in snapshot:
            labels = f'outcome="{outcome}"'
            lines.append(f"tactiqo_ingestion_publish_total{{{labels}}} {count}")
            for bucket_count, upper_bound in zip(
                buckets, _HISTOGRAM_BUCKETS, strict=True
            ):
                bucket_labels = f'{labels},le="{upper_bound:g}"'
                lines.append(
                    "tactiqo_ingestion_publish_duration_seconds_bucket"
                    f"{{{bucket_labels}}} {bucket_count}"
                )
            infinity_labels = f'{labels},le="+Inf"'
            lines.extend(
                (
                    "tactiqo_ingestion_publish_duration_seconds_bucket"
                    f"{{{infinity_labels}}} {count}",
                    f"tactiqo_ingestion_publish_duration_seconds_sum{{{labels}}} {total:.9g}",
                    f"tactiqo_ingestion_publish_duration_seconds_count{{{labels}}} {count}",
                )
            )
        return "\n".join(lines) + "\n"


class ObjectStorageMetrics:
    """Aggregate storage operation outcomes without keys, buckets, or byte labels."""

    def __init__(self) -> None:
        """Initialize a process-local fixed-cardinality registry."""
        self._lock = Lock()
        self._series: dict[tuple[str, str], tuple[int, float, tuple[int, ...]]] = {}

    def observe(self, operation: str, outcome: str, duration_ms: float) -> None:
        """Record a put/get/delete outcome and elapsed time using fixed labels."""
        safe_operation = (
            operation
            if isinstance(operation, str) and operation in _STORAGE_OPERATIONS
            else "other"
        )
        safe_outcome = (
            outcome if isinstance(outcome, str) and outcome in _STORAGE_OUTCOMES else "failure"
        )
        try:
            duration_seconds = float(duration_ms) / 1000
        except (OverflowError, TypeError, ValueError):
            duration_seconds = 0.0
        if not math.isfinite(duration_seconds):
            duration_seconds = 0.0
        duration_seconds = max(duration_seconds, 0.0)
        key = (safe_operation, safe_outcome)
        with self._lock:
            count, total, buckets = self._series.get(
                key, (0, 0.0, (0,) * len(_HISTOGRAM_BUCKETS))
            )
            observed_buckets = tuple(
                bucket_count + int(duration_seconds <= upper_bound)
                for bucket_count, upper_bound in zip(
                    buckets, _HISTOGRAM_BUCKETS, strict=True
                )
            )
            self._series[key] = (count + 1, total + duration_seconds, observed_buckets)

    def render_prometheus(self) -> str:
        """Render low-cardinality object-storage counters and latency histograms."""
        lines = [
            "# TYPE tactiqo_object_storage_operations_total counter",
            "# TYPE tactiqo_object_storage_operation_duration_seconds histogram",
        ]
        with self._lock:
            snapshot = tuple(sorted(self._series.items()))
        for (operation, outcome), (count, total, buckets) in snapshot:
            labels = f'operation="{operation}",outcome="{outcome}"'
            lines.append(f"tactiqo_object_storage_operations_total{{{labels}}} {count}")
            for bucket_count, upper_bound in zip(
                buckets, _HISTOGRAM_BUCKETS, strict=True
            ):
                bucket_labels = f'{labels},le="{upper_bound:g}"'
                lines.append(
                    "tactiqo_object_storage_operation_duration_seconds_bucket"
                    f"{{{bucket_labels}}} {bucket_count}"
                )
            infinity_labels = f'{labels},le="+Inf"'
            lines.extend(
                (
                    "tactiqo_object_storage_operation_duration_seconds_bucket"
                    f"{{{infinity_labels}}} {count}",
                    "tactiqo_object_storage_operation_duration_seconds_sum"
                    f"{{{labels}}} {total:.9g}",
                    f"tactiqo_object_storage_operation_duration_seconds_count{{{labels}}} {count}",
                )
            )
        return "\n".join(lines) + "\n"
