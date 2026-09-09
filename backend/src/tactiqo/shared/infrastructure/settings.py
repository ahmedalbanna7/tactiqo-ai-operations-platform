"""Typed runtime configuration with write-only secret values."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    local_actor_id: str = "local-dev-owner"
    local_organization_id: str = "local-dev-organization"
    local_classification: str = "internal"
    local_policy_version: str = "f1-local-v1"

    mcp_enabled: bool = True
    mcp_demo_url: str = "http://mcp-demo:8100/mcp"
    mcp_timeout_seconds: float = Field(default=20, ge=1, le=120)
    mcp_max_result_characters: int = Field(default=20_000, ge=1_000, le=200_000)

    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    ingestion_queue_name: str = "knowledge.parse.v1"
    ingestion_dead_letter_queue_name: str = "knowledge.parse.v1.dlq"
    ingestion_max_retries: int = Field(default=3, ge=0, le=10)

    knowledge_search_enabled: bool = False
    knowledge_local_fallback_enabled: bool = False
    onyx_base_url: str = "http://localhost:8080"
    onyx_service_token: SecretStr | None = None
    onyx_embedding_model: str = "intfloat/multilingual-e5-base"

    @model_validator(mode="after")
    def require_onyx_token_when_search_is_enabled(self) -> "Settings":
        """Reject an enabled knowledge provider without authentication.

        Returns:
            The validated settings instance.

        Raises:
            ValueError: If knowledge search is enabled without a non-empty
                Onyx service token.

        """
        token = (
            self.onyx_service_token.get_secret_value().strip()
            if self.onyx_service_token is not None
            else ""
        )
        if self.knowledge_search_enabled and not token:
            message = "Onyx service token is required when knowledge search is enabled."
            raise ValueError(message)
        openai_key = (
            self.openai_api_key.get_secret_value().strip()
            if self.openai_api_key is not None
            else ""
        )
        if self.model_provider is ModelProviderName.OPENAI and not openai_key:
            message = "OpenAI API key is required when the OpenAI provider is enabled."
            raise ValueError(message)
        if self.environment is RuntimeEnvironment.PRODUCTION:
            if self.model_provider is ModelProviderName.DETERMINISTIC:
                message = "The deterministic model provider is forbidden in production."
                raise ValueError(message)
            if self.local_development_context_enabled:
                message = "The local development execution context is forbidden in production."
                raise ValueError(message)
            if self.knowledge_local_fallback_enabled:
                message = "Local lexical knowledge fallback is forbidden in production."
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
            "knowledge_search_enabled": str(self.knowledge_search_enabled),
            "mcp_enabled": str(self.mcp_enabled),
        }
