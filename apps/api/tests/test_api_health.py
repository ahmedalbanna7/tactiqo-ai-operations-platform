"""HTTP API tests for liveness, readiness, and correlation behavior."""

from dataclasses import dataclass

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from tactiqo.shared.infrastructure.settings import RuntimeEnvironment, Settings
from tactiqo_api.factory import create_app


@dataclass(frozen=True, slots=True)
class HealthyProbe:
    """Test probe that always reports healthy."""

    name: str = "healthy-test"

    async def check(self) -> None:
        """Complete without error."""


@dataclass(frozen=True, slots=True)
class FailingProbe:
    """Test probe that simulates a provider outage."""

    name: str = "failing-test"

    async def check(self) -> None:
        """Raise a provider-like failure for boundary translation."""
        msg = "sensitive-provider-detail"
        raise ConnectionError(msg)


def _settings() -> Settings:
    """Build isolated settings without reading a developer environment file."""
    return Settings(
        _env_file=None,
        app_name="Tactiqo Test",
        app_version="test",
        environment=RuntimeEnvironment.TEST,
        database_url=SecretStr("postgresql+asyncpg://ignored"),
        redis_url=SecretStr("redis://ignored"),
        rabbitmq_url=SecretStr("amqp://ignored"),
        minio_endpoint="http://ignored",
        minio_access_key=SecretStr("ignored"),
        minio_secret_key=SecretStr("ignored"),
    )


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio only; the platform does not support multiple async runtimes."""
    return "asyncio"


@pytest.mark.anyio
async def test_liveness_returns_service_metadata_and_correlation_id() -> None:
    """Liveness succeeds independently of external dependency health."""
    transport = ASGITransport(app=create_app(_settings(), probes=[FailingProbe()]))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "healthy"
    assert response.headers["X-Correlation-ID"]


@pytest.mark.anyio
async def test_readiness_is_healthy_when_all_mandatory_probes_pass() -> None:
    """Readiness succeeds only when all configured probes pass."""
    transport = ASGITransport(app=create_app(_settings(), probes=[HealthyProbe()]))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["components"] == [
        {"name": "healthy-test", "status": "healthy", "detail": None}
    ]


@pytest.mark.anyio
async def test_readiness_fails_closed_and_redacts_provider_details() -> None:
    """Provider failures produce 503 without leaking exception contents."""
    transport = ASGITransport(app=create_app(_settings(), probes=[FailingProbe()]))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["status"] == "unhealthy"
    assert "sensitive-provider-detail" not in response.text
    assert response.json()["components"][0]["detail"] == "dependency_unavailable"


@pytest.mark.anyio
async def test_invalid_correlation_id_is_replaced() -> None:
    """Untrusted correlation values cannot be reflected into response headers."""
    transport = ASGITransport(app=create_app(_settings(), probes=[HealthyProbe()]))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health/live",
            headers={"X-Correlation-ID": "bad-value"},
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["X-Correlation-ID"] != "bad-value"


@pytest.mark.anyio
async def test_cors_preflight_allows_profile_put_from_local_ui() -> None:
    """The browser can reach owner profile activation after successful discovery."""
    transport = ASGITransport(app=create_app(_settings(), probes=[HealthyProbe()]))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/ai/profiles/default_reasoning_llm",
            headers={
                "Origin": "http://127.0.0.1:13000",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == status.HTTP_200_OK
    assert "PUT" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:13000"
