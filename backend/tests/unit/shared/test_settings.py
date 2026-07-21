"""Unit tests for secret-safe typed settings."""

import pytest
from pydantic import SecretStr, ValidationError

from tactiqo.shared.infrastructure.settings import Settings


def test_safe_summary_excludes_all_secrets_and_secret_urls() -> None:
    """Safe diagnostics never contain credentials or credential-bearing URLs."""
    marker = "must-not-leak"
    settings = Settings(
        _env_file=None,
        database_url=SecretStr(f"postgresql+asyncpg://{marker}"),
        redis_url=SecretStr(f"redis://{marker}"),
        rabbitmq_url=SecretStr(f"amqp://{marker}"),
        minio_endpoint="http://minio:9000",
        minio_access_key=SecretStr(marker),
        minio_secret_key=SecretStr(marker),
    )

    summary = str(settings.safe_summary())

    assert marker not in summary
    assert "database_url" not in summary
    assert "redis_url" not in summary
    assert "rabbitmq_url" not in summary


def test_knowledge_search_fails_closed_without_service_token() -> None:
    """Knowledge search cannot be enabled without provider authentication."""
    with pytest.raises(ValidationError, match="Onyx service token is required"):
        Settings(
            _env_file=None,
            database_url=SecretStr("postgresql+asyncpg://local"),
            redis_url=SecretStr("redis://local"),
            rabbitmq_url=SecretStr("amqp://local"),
            minio_endpoint="http://minio:9000",
            minio_access_key=SecretStr("local"),
            minio_secret_key=SecretStr("local"),
            knowledge_search_enabled=True,
            onyx_service_token=None,
        )
