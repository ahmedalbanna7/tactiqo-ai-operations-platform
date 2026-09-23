"""API metrics protection accepts the file-backed Docker scrape credential."""

from http import HTTPStatus
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from tactiqo.shared.infrastructure.settings import RuntimeEnvironment, Settings
from tactiqo_api.factory import create_app


@pytest.mark.anyio
async def test_api_metrics_scrape_uses_mounted_token_file(tmp_path: Path) -> None:
    """A protected scrape works with a mounted secret and denies absent bearer auth."""
    token = "mounted-api-scrape-token"  # noqa: S105 - test-only bearer credential
    token_file = tmp_path / "metrics-token"
    token_file.write_text(token, encoding="utf-8")
    settings = Settings(
        _env_file=None,
        environment=RuntimeEnvironment.TEST,
        database_url=SecretStr("postgresql+asyncpg://ignored"),
        redis_url=SecretStr("redis://ignored"),
        rabbitmq_url=SecretStr("amqp://ignored"),
        minio_endpoint="http://ignored",
        minio_access_key=SecretStr("ignored"),
        minio_secret_key=SecretStr("ignored"),
        metrics_auth_token_file=token_file,
    )
    app = create_app(settings)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.get("/internal/metrics")
        allowed = await client.get(
            "/internal/metrics",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert denied.status_code == HTTPStatus.NOT_FOUND
    assert allowed.status_code == HTTPStatus.OK
    assert token not in allowed.text
