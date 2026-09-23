"""Structured request telemetry is bounded to a reviewed, secret-free field allowlist."""

import io
import json
import logging
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from starlette.types import Message, Receive, Scope, Send

from tactiqo.shared.infrastructure.settings import RuntimeEnvironment, Settings
from tactiqo_api.factory import create_app
from tactiqo_api.observability import HttpRequestMetrics, HttpTelemetryMiddleware, SafeJsonFormatter

HTTP_OK = 200
HTTP_NOT_FOUND = 404
MESSAGE_COUNT = 2
SAMPLE_DURATION_MS = 1.25


def _settings(
    *,
    metrics_auth_token: SecretStr | None = None,
    metrics_auth_token_file: Path | None = None,
) -> Settings:
    """Build isolated API settings without loading a developer environment file."""
    return Settings(
        _env_file=None,
        app_name="Tactiqo Observability Test",
        app_version="test",
        environment=RuntimeEnvironment.TEST,
        database_url=SecretStr("postgresql+asyncpg://ignored"),
        redis_url=SecretStr("redis://ignored"),
        rabbitmq_url=SecretStr("amqp://ignored"),
        minio_endpoint="http://ignored",
        minio_access_key=SecretStr("ignored"),
        minio_secret_key=SecretStr("ignored"),
        metrics_auth_token=metrics_auth_token,
        metrics_auth_token_file=metrics_auth_token_file,
    )


def test_blank_metrics_credential_is_treated_as_unset() -> None:
    """Compose's optional blank environment value keeps local scraping enabled."""
    settings = _settings(metrics_auth_token=SecretStr("  "))

    assert settings.metrics_auth_token is None


def test_json_formatter_ignores_unapproved_log_record_fields() -> None:
    """Even accidental extra fields such as tokens are omitted from serialized logs."""
    record = logging.LogRecord(
        "tactiqo.http",
        logging.INFO,
        "routes.py",
        10,
        "http.request.complete Bearer secret-token",
        (),
        None,
    )
    record.correlation_id = str(uuid4())
    record.method = "GET"
    record.route = "/health/live"
    record.status_code = HTTP_OK
    record.duration_ms = SAMPLE_DURATION_MS
    record.authorization = "Bearer secret-token"
    record.query = "?token=secret-token"

    rendered = SafeJsonFormatter().format(record)
    payload = json.loads(rendered)

    assert payload["event"] == "http.request.complete"
    assert payload["method"] == "GET"
    assert payload["route"] == "/health/live"
    assert payload["status_code"] == HTTP_OK
    assert payload["duration_ms"] == SAMPLE_DURATION_MS
    assert "authorization" not in payload
    assert "query" not in payload
    assert "secret-token" not in rendered


@pytest.mark.anyio
async def test_http_telemetry_logs_route_template_without_query_string() -> None:
    """HTTP telemetry records a canonical route and correlation but never query data."""
    stream = io.StringIO()
    logger = logging.getLogger(f"test.http.{uuid4()}")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SafeJsonFormatter())
    logger.addHandler(handler)
    correlation_id = str(uuid4())
    metrics = HttpRequestMetrics()

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        del receive
        scope["route"] = SimpleNamespace(path="/documents/{document_id}")
        await send(
            {
                "type": "http.response.start",
                "status": HTTP_OK,
                "headers": [(b"x-correlation-id", correlation_id.encode("ascii"))],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/documents/123",
        "query_string": b"token=must-not-be-logged",
        "headers": [],
    }
    await HttpTelemetryMiddleware(app, logger, metrics)(scope, receive, send)

    log_entry = json.loads(stream.getvalue())
    assert log_entry["correlation_id"] == correlation_id
    assert log_entry["route"] == "/documents/{document_id}"
    assert log_entry["status_code"] == HTTP_OK
    assert "must-not-be-logged" not in stream.getvalue()
    assert len(messages) == MESSAGE_COUNT
    rendered_metrics = metrics.render_prometheus()
    assert 'route="/documents/{document_id}"' in rendered_metrics
    assert "tactiqo_http_requests_total" in rendered_metrics
    assert "tactiqo_http_request_duration_seconds_count" in rendered_metrics
    assert "123" not in rendered_metrics


def test_metrics_use_only_bounded_method_and_status_labels() -> None:
    """Untrusted method values are collapsed, and metric labels carry no actor data."""
    metrics = HttpRequestMetrics()
    metrics.observe("TRACE\nforged", "/health/live", 503, 4.5)

    rendered = metrics.render_prometheus()

    assert 'method="OTHER"' in rendered
    assert 'status_class="5xx"' in rendered
    assert "forged" not in rendered
    assert "organization_id" not in rendered


@pytest.mark.anyio
async def test_metrics_scrape_requires_configured_bearer_token() -> None:
    """A configured metrics endpoint rejects missing credentials without disclosing itself."""
    scrape_credential = "private-scrape-token"
    app = create_app(_settings(metrics_auth_token=SecretStr(scrape_credential)))
    app.state.ai_bank = SimpleNamespace(
        render_metrics=lambda: "tactiqo_ai_provider_calls_total{} 0\n"
    )
    app.state.tool_call_metrics = SimpleNamespace(
        render_prometheus=lambda: "tactiqo_tool_calls_total{} 0\n"
    )
    app.state.knowledge_retrieval_metrics = SimpleNamespace(
        render_prometheus=lambda: "tactiqo_knowledge_retrieval_total{} 0\n"
    )
    app.state.ingestion_queue_metrics = SimpleNamespace(
        render_prometheus=lambda: "tactiqo_ingestion_publish_total{} 0\n"
    )
    app.state.object_storage_metrics = SimpleNamespace(
        render_prometheus=lambda: "tactiqo_object_storage_operations_total{} 0\n"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.get("/internal/metrics")
        denied_non_ascii = await client.get(
            "/internal/metrics", headers={b"Authorization": b"Bearer not-\xff-valid"}
        )
        allowed = await client.get(
            "/internal/metrics",
            headers={"Authorization": f"Bearer {scrape_credential}"},
        )

    assert denied.status_code == HTTPStatus.NOT_FOUND
    assert denied_non_ascii.status_code == HTTPStatus.NOT_FOUND
    assert allowed.status_code == HTTPStatus.OK
    assert "tactiqo_http_requests_total" in allowed.text
    assert "tactiqo_ai_provider_calls_total" in allowed.text
    assert "tactiqo_tool_calls_total" in allowed.text
    assert "tactiqo_knowledge_retrieval_total" in allowed.text
    assert "tactiqo_ingestion_publish_total" in allowed.text
    assert "tactiqo_object_storage_operations_total" in allowed.text
    assert scrape_credential not in allowed.text


@pytest.mark.anyio
async def test_metrics_scrape_is_disabled_outside_dev_without_token() -> None:
    """Staging and production-like deployments fail closed when scrape auth is absent."""
    settings = _settings().model_copy(
        update={"environment": RuntimeEnvironment.STAGING}
    )
    app = create_app(settings)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/internal/metrics")

    assert response.status_code == HTTP_NOT_FOUND
