"""Thin system routes delegating readiness to the application service."""

from fastapi import APIRouter, Request, Response, status

from tactiqo.shared.application.health import ReadinessService
from tactiqo.shared.domain.health import HealthStatus
from tactiqo.shared.infrastructure.settings import Settings
from tactiqo_api.schemas import (
    ComponentHealthResponse,
    HealthResponse,
    ServiceInfoResponse,
)

router = APIRouter(tags=["system"])


def _settings(request: Request) -> Settings:
    """Read process settings from the application composition state."""
    settings: Settings = request.app.state.settings
    return settings


def _readiness_service(request: Request) -> ReadinessService:
    """Read the readiness use case from the application composition state."""
    service: ReadinessService = request.app.state.readiness_service
    return service


@router.get("/")
async def service_info(request: Request) -> ServiceInfoResponse:
    """Return non-sensitive service identity metadata."""
    settings = _settings(request)
    return ServiceInfoResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    )


@router.get("/health/live")
async def liveness(request: Request) -> HealthResponse:
    """Confirm the API process can handle requests without dependency checks."""
    settings = _settings(request)
    return HealthResponse(
        status=HealthStatus.HEALTHY.value,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    )


@router.get(
    "/health/ready",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def readiness(request: Request, response: Response) -> HealthResponse:
    """Return fail-closed readiness for all mandatory local dependencies."""
    settings = _settings(request)
    health = await _readiness_service(request).evaluate()
    if health.status is HealthStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status=health.status.value,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        components=[
            ComponentHealthResponse(
                name=component.name,
                status=component.status.value,
                detail=component.detail,
            )
            for component in health.components
        ],
    )
