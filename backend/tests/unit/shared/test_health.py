"""Unit tests for deterministic readiness aggregation."""

import asyncio
from dataclasses import dataclass

from tactiqo.shared.application.health import ReadinessService
from tactiqo.shared.domain.health import ComponentHealth, HealthStatus, ReadinessHealth


@dataclass(frozen=True, slots=True)
class ImmediateProbe:
    """Test probe that completes immediately."""

    name: str = "immediate"

    async def check(self) -> None:
        """Complete without waiting."""


@dataclass(frozen=True, slots=True)
class SlowProbe:
    """Test probe that exceeds the individual readiness budget."""

    name: str = "slow"

    async def check(self) -> None:
        """Sleep beyond the configured test timeout."""
        await asyncio.sleep(0.05)


def test_readiness_is_unhealthy_when_any_component_fails() -> None:
    """One failed mandatory dependency makes the aggregate unavailable."""
    health = ReadinessHealth.from_components(
        (
            ComponentHealth(name="postgresql", status=HealthStatus.HEALTHY),
            ComponentHealth(name="rabbitmq", status=HealthStatus.UNHEALTHY),
        )
    )

    assert health.status is HealthStatus.UNHEALTHY


def test_probe_timeout_does_not_discard_other_component_results() -> None:
    """One timeout is isolated while completed probe results remain accurate."""
    service = ReadinessService(
        probes=(ImmediateProbe(), SlowProbe()),
        timeout_seconds=0.01,
    )

    health = asyncio.run(service.evaluate())
    components = {component.name: component for component in health.components}

    assert components["immediate"].status is HealthStatus.HEALTHY
    assert components["slow"].status is HealthStatus.UNHEALTHY
    assert components["slow"].detail == "check_timeout"
