"""Safe structured HTTP telemetry for the API process."""

import json
import logging
import time
from datetime import UTC, datetime
from threading import Lock
from typing import ClassVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_CONFIGURED_LOGGERS: set[str] = set()
_HISTOGRAM_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"})

class SafeJsonFormatter(logging.Formatter):
    """Serialize a strict allowlist of non-sensitive request telemetry fields."""

    _FIELDS: ClassVar[tuple[str, ...]] = (
        "correlation_id",
        "method",
        "route",
        "status_code",
        "duration_ms",
    )

    def format(self, record: logging.LogRecord) -> str:
        """Return one JSON object, excluding arbitrary LogRecord attributes."""
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "event": "http.request.complete",
        }
        for field in self._FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_http_telemetry_logger() -> logging.Logger:
    """Configure an isolated stdout logger that emits only allowlisted JSON fields."""
    logger = logging.getLogger("tactiqo.http")
    if logger.name not in _CONFIGURED_LOGGERS:
        handler = logging.StreamHandler()
        handler.setFormatter(SafeJsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _CONFIGURED_LOGGERS.add(logger.name)
    return logger


class HttpRequestMetrics:
    """Aggregate bounded per-route request counters and latency histograms."""

    def __init__(self) -> None:
        """Initialize process-local counters with no tenant or user labels."""
        self._lock = Lock()
        self._series: dict[tuple[str, str, str], tuple[int, float, tuple[int, ...]]] = {}

    def observe(
        self, method: str, route: str, status_code: int, duration_ms: float
    ) -> None:
        """Record one request using only method, route template and status class."""
        safe_method = method if method in _ALLOWED_METHODS else "OTHER"
        safe_route = route if route.startswith("/") else "unmatched"
        status_class = f"{status_code // 100}xx"
        key = (safe_method, safe_route, status_class)
        duration_seconds = max(duration_ms, 0.0) / 1000
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
        """Render bounded Prometheus text exposition without secret/high-cardinality labels."""
        lines = [
            "# TYPE tactiqo_http_requests_total counter",
            "# TYPE tactiqo_http_request_duration_seconds histogram",
        ]
        with self._lock:
            snapshot = tuple(sorted(self._series.items()))
        for (method, route, status_class), (count, total, buckets) in snapshot:
            labels = self._labels(method, route, status_class)
            lines.append(f"tactiqo_http_requests_total{{{labels}}} {count}")
            for bucket_count, upper_bound in zip(
                buckets, _HISTOGRAM_BUCKETS, strict=True
            ):
                bucket_labels = self._labels(
                    method, route, status_class, le=f"{upper_bound:g}"
                )
                lines.append(
                    "tactiqo_http_request_duration_seconds_bucket"
                    f"{{{bucket_labels}}} {bucket_count}"
                )
            infinity_labels = self._labels(method, route, status_class, le="+Inf")
            lines.extend(
                (
                    "tactiqo_http_request_duration_seconds_bucket"
                    f"{{{infinity_labels}}} {count}",
                    f"tactiqo_http_request_duration_seconds_sum{{{labels}}} {total:.9g}",
                    f"tactiqo_http_request_duration_seconds_count{{{labels}}} {count}",
                )
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _labels(method: str, route: str, status_class: str, *, le: str | None = None) -> str:
        """Escape stable label values for Prometheus exposition."""
        escaped_route = route.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        labels = [
            f'method="{method}"',
            f'route="{escaped_route}"',
            f'status_class="{status_class}"',
        ]
        if le is not None:
            labels.append(f'le="{le}"')
        return ",".join(labels)


class HttpTelemetryMiddleware:
    """Emit one safe completion event per HTTP request."""

    def __init__(
        self, app: ASGIApp, logger: logging.Logger, metrics: HttpRequestMetrics
    ) -> None:
        """Wrap an ASGI application with a dedicated allowlist logger."""
        self._app = app
        self._logger = logger
        self._metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Capture status, safe route template, correlation and elapsed time only."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500
        correlation_id = "unavailable"

        async def capture_response(message: Message) -> None:
            nonlocal status_code, correlation_id
            if message["type"] == "http.response.start":
                status_code = message["status"]
                for name, value in message.get("headers", []):
                    if name.lower() == b"x-correlation-id":
                        correlation_id = value.decode("ascii", errors="ignore")
                        break
            await send(message)

        try:
            await self._app(scope, receive, capture_response)
        finally:
            route = scope.get("route")
            route_template = getattr(route, "path", "unmatched")
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            method = scope.get("method", "unknown")
            self._metrics.observe(method, route_template, status_code, duration_ms)
            self._logger.info(
                "http.request.complete",
                extra={
                    "correlation_id": correlation_id,
                    "method": method,
                    "route": route_template,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
