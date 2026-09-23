"""FastAPI composition root with explicit dependency injection."""

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tactiqo.shared.application.health import ReadinessProbe, ReadinessService
from tactiqo.shared.infrastructure.readiness import (
    MinIOProbe,
    PostgreSQLProbe,
    RabbitMQProbe,
    RedisProbe,
)
from tactiqo.shared.infrastructure.settings import Settings
from tactiqo_api.composition import build_lifespan
from tactiqo_api.middleware import CorrelationIdMiddleware
from tactiqo_api.observability import (
    HttpRequestMetrics,
    HttpTelemetryMiddleware,
    configure_http_telemetry_logger,
)
from tactiqo_api.routes import api_router, router


def build_default_probes(settings: Settings) -> tuple[ReadinessProbe, ...]:
    """Compose local-core probes from validated settings.

    Args:
        settings: Validated process configuration containing write-only secrets.

    Returns:
        Mandatory dependency probes for PostgreSQL, Redis, RabbitMQ, and MinIO.

    """
    timeout = settings.readiness_timeout_seconds
    return (
        PostgreSQLProbe(
            dsn=settings.database_url.get_secret_value(),
            timeout_seconds=timeout,
        ),
        RedisProbe(
            url=settings.redis_url.get_secret_value(),
            timeout_seconds=timeout,
        ),
        RabbitMQProbe(
            url=settings.rabbitmq_url.get_secret_value(),
            timeout_seconds=timeout,
        ),
        MinIOProbe(endpoint=settings.minio_endpoint, timeout_seconds=timeout),
    )


def create_app(
    settings: Settings,
    probes: Sequence[ReadinessProbe] | None = None,
) -> FastAPI:
    """Create the API with explicit configuration and replaceable probes.

    Args:
        settings: Validated runtime configuration.
        probes: Optional probe set for tests or a deployment-specific composition.

    Returns:
        Fully composed FastAPI application.

    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.environment.value != "production" else None,
        redoc_url="/redoc" if settings.environment.value != "production" else None,
        lifespan=build_lifespan(settings),
    )
    app.state.settings = settings
    app.state.readiness_service = ReadinessService(
        probes=build_default_probes(settings) if probes is None else probes,
        timeout_seconds=settings.readiness_timeout_seconds,
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Correlation-ID", "Last-Event-ID"],
        expose_headers=["X-Correlation-ID"],
    )
    http_metrics = HttpRequestMetrics()
    app.state.http_request_metrics = http_metrics
    app.add_middleware(
        HttpTelemetryMiddleware,
        logger=configure_http_telemetry_logger(),
        metrics=http_metrics,
    )
    app.include_router(router)
    app.include_router(api_router)
    return app
