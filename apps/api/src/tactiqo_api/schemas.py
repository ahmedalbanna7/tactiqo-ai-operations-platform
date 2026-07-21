"""Transport schemas for system health endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class ComponentHealthResponse(BaseModel):
    """Expose a safe readiness result for one dependency."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    """Expose service liveness or aggregate readiness."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    version: str
    environment: str
    components: list[ComponentHealthResponse] = Field(default_factory=list)


class ServiceInfoResponse(BaseModel):
    """Expose non-sensitive service identity information."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    environment: str
