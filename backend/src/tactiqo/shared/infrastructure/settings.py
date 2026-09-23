"""Typed runtime configuration with write-only secret values."""

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_WORK_ENVELOPE_KEY = "local-only-work-envelope-key-change-me"
MIN_WORK_ENVELOPE_KEY_CHARACTERS = 32


class RuntimeEnvironment(StrEnum):
    """Supported deployment environment identifiers."""

    LOCAL = "local"
    TEST = "test"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ModelProviderName(StrEnum):
    """Supported model-provider adapters."""

    DETERMINISTIC = "deterministic"
    OPENAI = "openai"
    AI_BANK = "ai_bank"


class Settings(BaseSettings):
    """Validate process configuration without returning secret values.

    Secret-bearing fields use `SecretStr`, remain excluded from safe summaries,
    and must never be included in logs, traces, events, prompts, or API output.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TACTIQO_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Tactiqo AI Operations Platform"
    app_version: str = "0.1.0"
    environment: RuntimeEnvironment = RuntimeEnvironment.LOCAL
    log_level: str = "INFO"
    metrics_auth_token: SecretStr | None = None
    metrics_auth_token_file: Path | None = None
    metrics_port: int = Field(default=8101, ge=1, le=65535)
    api_host: str = "0.0.0.0"  # noqa: S104 - intentional container bind
    api_port: int = Field(default=8000, ge=1, le=65535)
    readiness_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    cors_allowed_origins: str = "http://localhost:13000,http://127.0.0.1:13000"

    database_url: SecretStr
    checkpoint_database_url: SecretStr | None = None
    redis_url: SecretStr
    rabbitmq_url: SecretStr
    minio_endpoint: str
    minio_access_key: SecretStr
    minio_secret_key: SecretStr
    minio_bucket: str = "tactiqo-knowledge"

    model_provider: ModelProviderName = ModelProviderName.DETERMINISTIC
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-sol"
    openai_reasoning_effort: Literal[
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ] = "low"
    agent_max_iterations: int = Field(default=6, ge=1, le=20)
    agent_max_tool_calls: int = Field(default=4, ge=0, le=12)
    agent_timeout_seconds: float = Field(default=90, ge=5, le=600)
    agent_max_concurrent_runs: int = Field(default=4, ge=1, le=32)
    agent_event_poll_seconds: float = Field(default=0.2, ge=0.05, le=2)

    local_development_context_enabled: bool = True
    local_actor_id: str = "00000000-0000-4000-8000-000000000001"
    local_organization_id: str = "local-dev-organization"
    local_classification: str = "internal"
    local_policy_version: str = "f1-local-v1"

    oidc_enabled: bool = False
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_client_id: SecretStr | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_authorization_endpoint: str = ""
    oidc_token_endpoint: str = ""
    oidc_jwks_uri: str = ""
    oidc_state_signing_key: SecretStr | None = None
    oidc_redirect_uri: str = "http://127.0.0.1:18000/api/v1/auth/callback"
    oidc_session_cookie_name: str = "tactiqo_session"
    oidc_session_ttl_seconds: int = Field(default=3600, ge=300, le=86400)

    mcp_enabled: bool = True
    mcp_demo_enabled: bool = True
    mcp_demo_url: str = "http://mcp-demo:8100/mcp"
    mcp_jira_enabled: bool = False
    mcp_jira_url: str = "https://mcp.atlassian.com/v2/mcp?tools=all"
    mcp_jira_authorization: SecretStr | None = None
    mcp_jira_oauth_storage: str | None = None
    mcp_slack_enabled: bool = False
    mcp_slack_url: str = ""
    mcp_slack_authorization: SecretStr | None = None
    mcp_timeout_seconds: float = Field(default=20, ge=1, le=120)
    mcp_max_result_characters: int = Field(default=20_000, ge=1_000, le=200_000)
    integration_connections_enabled: bool = False
    credential_encryption_key: SecretStr | None = None
    oauth_public_api_base_url: str = "http://127.0.0.1:18000"
    oauth_web_base_url: str = "http://127.0.0.1:13000"
    slack_oauth_client_id: SecretStr | None = None
    slack_oauth_client_secret: SecretStr | None = None

    max_upload_bytes: int = Field(default=100 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    ingestion_queue_name: str = "knowledge.parse.v1"
    ingestion_dead_letter_queue_name: str = "knowledge.parse.v1.dlq"
    ingestion_max_retries: int = Field(default=3, ge=0, le=10)
    work_envelope_signing_key: SecretStr = SecretStr(LOCAL_WORK_ENVELOPE_KEY)

    @model_validator(mode="after")
    def validate_provider_and_production_safety(self) -> "Settings":  # noqa: C901
        """Reject unsafe model and local-development production settings.

        Returns:
            The validated settings instance.

        Raises:
            ValueError: If a required model secret is absent or production uses
                a development-only implementation.

        """
        if (
            self.metrics_auth_token is not None
            and not self.metrics_auth_token.get_secret_value().strip()
        ):
            self.metrics_auth_token = None
        openai_key = (
            self.openai_api_key.get_secret_value().strip()
            if self.openai_api_key is not None
            else ""
        )
        if self.model_provider is ModelProviderName.OPENAI and not openai_key:
            message = "OpenAI API key is required when the OpenAI provider is enabled."
            raise ValueError(message)
        jira_authorization = (
            self.mcp_jira_authorization.get_secret_value().strip()
            if self.mcp_jira_authorization
            else ""
        )
        if self.mcp_jira_enabled and not (
            jira_authorization or (self.mcp_jira_oauth_storage or "").strip()
        ):
            message = "Jira MCP authorization is required: configure bearer or OAuth storage."
            raise ValueError(message)
        slack_authorization = (
            self.mcp_slack_authorization.get_secret_value().strip()
            if self.mcp_slack_authorization
            else ""
        )
        if self.mcp_slack_enabled and not slack_authorization:
            message = "Slack MCP authorization is required when enabled."
            raise ValueError(message)
        if self.mcp_slack_enabled and not self.mcp_slack_url.strip():
            message = "Slack MCP URL is required when enabled."
            raise ValueError(message)
        encryption_key = (
            self.credential_encryption_key.get_secret_value().strip()
            if self.credential_encryption_key
            else ""
        )
        if self.integration_connections_enabled and not encryption_key:
            message = "Credential encryption key is required for SaaS integrations."
            raise ValueError(message)
        if (
            self.environment
            not in {
                RuntimeEnvironment.LOCAL,
                RuntimeEnvironment.TEST,
                RuntimeEnvironment.DEVELOPMENT,
            }
            and self.local_development_context_enabled
        ):
            message = (
                "The local development execution context is forbidden outside local environments."
            )
            raise ValueError(message)
        if self.environment is RuntimeEnvironment.PRODUCTION:
            if self.model_provider is ModelProviderName.DETERMINISTIC:
                message = "The deterministic model provider is forbidden in production."
                raise ValueError(message)
            if not self.oidc_enabled or not all(
                (
                    self.oidc_issuer,
                    self.oidc_audience,
                    self.oidc_authorization_endpoint,
                    self.oidc_token_endpoint,
                    self.oidc_jwks_uri,
                    self.oidc_client_id,
                    self.oidc_client_secret,
                    self.oidc_state_signing_key,
                )
            ):
                message = "Production requires a configured OIDC identity provider."
                raise ValueError(message)
            work_key = self.work_envelope_signing_key.get_secret_value()
            if (
                work_key == LOCAL_WORK_ENVELOPE_KEY
                or len(work_key) < MIN_WORK_ENVELOPE_KEY_CHARACTERS
            ):
                message = "Production requires an independent work-envelope signing key."
                raise ValueError(message)
        return self

    @property
    def checkpoint_dsn(self) -> str:
        """Return a psycopg-compatible checkpoint DSN without exposing it publicly."""
        if self.checkpoint_database_url is not None:
            return self.checkpoint_database_url.get_secret_value()
        return self.database_url.get_secret_value().replace(
            "postgresql+asyncpg://", "postgresql://"
        )

    @property
    def effective_metrics_auth_token(self) -> SecretStr | None:
        """Resolve a scrape token from an explicit secret or a mounted secret file."""
        if self.metrics_auth_token is not None:
            value = self.metrics_auth_token.get_secret_value().strip()
            if value:
                return SecretStr(value)
        if self.metrics_auth_token_file is None:
            return None
        try:
            value = self.metrics_auth_token_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return SecretStr(value) if value else None

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        """Return normalized browser origins for CORS configuration."""
        return tuple(
            origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()
        )

    def safe_summary(self) -> dict[str, str | int | float]:
        """Return non-sensitive runtime metadata suitable for logs and diagnostics.

        Returns:
            A dictionary that intentionally excludes all credentials and URLs that
            may embed credentials.

        """
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "environment": self.environment.value,
            "log_level": self.log_level,
            "api_host": self.api_host,
            "api_port": self.api_port,
            "readiness_timeout_seconds": self.readiness_timeout_seconds,
            "model_provider": self.model_provider.value,
            "openai_model": self.openai_model,
            "mcp_enabled": str(self.mcp_enabled),
        }
