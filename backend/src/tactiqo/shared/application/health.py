"""Readiness orchestration independent of transport and vendor clients."""

import asyncio
import logging
from collections.abc import Sequence
from typing import Protocol

from tactiqo.shared.domain.health import ComponentHealth, HealthStatus, ReadinessHealth

LOGGER = logging.getLogger(__name__)


class ReadinessProbe(Protocol):
    """Contract implemented by one mandatory dependency readiness probe."""

    @property
    def name(self) -> str:
        """Return the stable, non-sensitive component name."""
        ...

    async def check(self) -> None:
        """Raise a controlled provider exception when the dependency is unavailable."""
        ...


class ReadinessService:
    """Run mandatory readiness probes concurrently with a global time budget."""

    def __init__(self, probes: Sequence[ReadinessProbe], timeout_seconds: float) -> None:
        """Create the service with an immutable probe set and bounded timeout.

        Args:
            probes: Mandatory dependency checks.
            timeout_seconds: Maximum duration allowed for all checks.

        Raises:
            ValueError: When the timeout is not positive.

        """
        if timeout_seconds <= 0:
            msg = "Readiness timeout must be positive."
            raise ValueError(msg)
        self._probes = tuple(probes)
        self._timeout_seconds = timeout_seconds

    async def evaluate(self) -> ReadinessHealth:
        """Evaluate every probe and return a redacted fail-closed result.

        Returns:
            Aggregate readiness plus a stable status for each dependency.

        Side Effects:
            Performs bounded network calls through injected infrastructure probes.

        """
        checks = tuple(
            self._safe_check(probe, timeout_seconds=self._timeout_seconds) for probe in self._probes
        )
        components = tuple(await asyncio.gather(*checks))
        return ReadinessHealth.from_components(components)

    @staticmethod
    async def _safe_check(
        probe: ReadinessProbe,
        timeout_seconds: float,
    ) -> ComponentHealth:
        """Translate a provider failure into a safe component result.

        Args:
            probe: Infrastructure probe whose raw exception must not reach the API.
            timeout_seconds: Maximum duration for this individual dependency.

        Returns:
            Healthy on success or a redacted unhealthy result on failure.

        """
        try:
            await asyncio.wait_for(probe.check(), timeout=timeout_seconds)
        except TimeoutError:
            LOGGER.warning(
                "readiness_component_timeout",
                extra={"component": probe.name, "timeout": timeout_seconds},
            )
            return ComponentHealth(
                name=probe.name,
                status=HealthStatus.UNHEALTHY,
                detail="check_timeout",
            )
        except Exception:
            LOGGER.exception("readiness_component_failed", extra={"component": probe.name})
            return ComponentHealth(
                name=probe.name,
                status=HealthStatus.UNHEALTHY,
                detail="dependency_unavailable",
            )
        return ComponentHealth(name=probe.name, status=HealthStatus.HEALTHY)
