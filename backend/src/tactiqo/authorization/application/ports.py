"""Ports used by the policy compiler."""

from typing import Protocol

from tactiqo.authorization.domain.models import (
    EffectiveToolGrantSummary,
    OrganizationUnitScope,
    PolicyDecision,
    PolicyResource,
    PolicyRule,
)
from tactiqo.shared.domain.execution import ExecutionContext


class PolicyRepository(Protocol):
    """Load active rules in one tenant and policy version."""

    async def list_rules(self, organization_id: str, policy_version: str) -> list[PolicyRule]:
        """Return active sanitized rules."""


class EffectiveToolAccessReader(Protocol):
    """Read bounded, secret-free integration grants for a resolved subject."""

    async def read(self, context: ExecutionContext) -> tuple[list[EffectiveToolGrantSummary], bool]:
        """Return effective grants and whether the result was truncated."""


class AccessPreviewUnitReader(Protocol):
    """Resolve one active tenant unit without exposing its contents to the preview."""

    async def read_unit(
        self, organization_id: str, kind: str, unit_id: str
    ) -> OrganizationUnitScope | None:
        """Return validated hierarchy metadata for one exact tenant-owned unit."""


class DecisionAuditPort(Protocol):
    """Persist a sanitized explanation for security review."""

    async def record(
        self,
        context: ExecutionContext,
        resource: PolicyResource,
        action: str,
        decision: PolicyDecision,
    ) -> None:
        """Record metadata only, never request or resource content."""


class DecisionCachePort(Protocol):
    """Bounded cache for safe allow decisions only."""

    async def get(self, key: str) -> PolicyDecision | None:
        """Return a non-expired decision."""

    async def put(self, key: str, decision: PolicyDecision) -> None:
        """Store one bounded allow decision."""
