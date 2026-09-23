"""Unit tests for secret-safe typed settings."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from tactiqo.shared.infrastructure.settings import ModelProviderName, Settings


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


def test_metrics_auth_token_is_loaded_from_secret_file(tmp_path: Path) -> None:
    """Docker-mounted scrape credentials remain typed secrets and absent from summaries."""
    marker = "mounted-scrape-token"
    token_file = tmp_path / "metrics-token"
    token_file.write_text(marker, encoding="utf-8")
    settings = Settings(
        _env_file=None,
        database_url=SecretStr("postgresql+asyncpg://local"),
        redis_url=SecretStr("redis://local"),
        rabbitmq_url=SecretStr("amqp://local"),
        minio_endpoint="http://minio:9000",
        minio_access_key=SecretStr("local"),
        minio_secret_key=SecretStr("local"),
        metrics_auth_token_file=token_file,
    )

    assert settings.effective_metrics_auth_token == SecretStr(marker)
    assert marker not in str(settings.safe_summary())


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"mcp_jira_enabled": True}, "Jira MCP authorization is required"),
        (
            {"mcp_slack_enabled": True, "mcp_slack_url": "https://slack.example/mcp"},
            "Slack MCP authorization is required",
        ),
    ],
)
def test_enabled_remote_mcp_requires_authorization(
    overrides: dict[str, object],
    message: str,
) -> None:
    """Remote integrations fail closed when no authorization is configured."""
    with pytest.raises(ValidationError, match=message):
        Settings(
            _env_file=None,
            database_url=SecretStr("postgresql+asyncpg://local"),
            redis_url=SecretStr("redis://local"),
            rabbitmq_url=SecretStr("amqp://local"),
            minio_endpoint="http://minio:9000",
            minio_access_key=SecretStr("local"),
            minio_secret_key=SecretStr("local"),
            **overrides,
        )


def test_production_requires_oidc_when_local_identity_is_disabled() -> None:
    """Production cannot start without a real configured identity boundary."""
    with pytest.raises(ValidationError, match="OIDC identity provider"):
        Settings(
            _env_file=None,
            environment="production",
            local_development_context_enabled=False,
            model_provider=ModelProviderName.OPENAI,
            openai_api_key=SecretStr("test-only"),
            database_url=SecretStr("postgresql+asyncpg://local"),
            redis_url=SecretStr("redis://local"),
            rabbitmq_url=SecretStr("amqp://local"),
            minio_endpoint="http://minio:9000",
            minio_access_key=SecretStr("local"),
            minio_secret_key=SecretStr("local"),
        )


def test_staging_rejects_local_development_identity() -> None:
    """Shared environments cannot impersonate the local development owner."""
    with pytest.raises(ValidationError, match="forbidden outside local environments"):
        Settings(
            _env_file=None,
            environment="staging",
            local_development_context_enabled=True,
            database_url=SecretStr("postgresql+asyncpg://local"),
            redis_url=SecretStr("redis://local"),
            rabbitmq_url=SecretStr("amqp://local"),
            minio_endpoint="http://minio:9000",
            minio_access_key=SecretStr("local"),
            minio_secret_key=SecretStr("local"),
        )
