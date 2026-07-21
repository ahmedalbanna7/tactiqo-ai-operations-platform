"""Typed runtime configuration with write-only secret values."""

from enum import StrEnum

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeEnvironment(StrEnum):
    """Supported deployment environment identifiers."""

    LOCAL = "local"
    TEST = "test"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


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

    database_url: SecretStr
    redis_url: SecretStr
    rabbitmq_url: SecretStr
    minio_endpoint: str
    minio_access_key: SecretStr
    minio_secret_key: SecretStr

    knowledge_search_enabled: bool = False
    onyx_base_url: str = "http://localhost:8080"
    onyx_service_token: SecretStr | None = None

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
        return self

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
        }
