"""Dependency-neutral health value objects."""

from dataclasses import dataclass
from enum import StrEnum


class HealthStatus(StrEnum):
    """Represent the deterministic state of a health check."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    """Describe one dependency check without exposing sensitive details."""

    name: str
    status: HealthStatus
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessHealth:
    """Aggregate the readiness of mandatory platform dependencies."""

    status: HealthStatus
    components: tuple[ComponentHealth, ...]

    @classmethod
    def from_components(
        cls,
        components: tuple[ComponentHealth, ...],
    ) -> "ReadinessHealth":
        """Build readiness from component results using fail-closed semantics.

        Args:
            components: Results for every configured mandatory dependency.

        Returns:
            An unhealthy aggregate when any mandatory dependency is unhealthy.

        """
        aggregate = (
            HealthStatus.HEALTHY
            if all(component.status is HealthStatus.HEALTHY for component in components)
            else HealthStatus.UNHEALTHY
        )
        return cls(status=aggregate, components=components)
