"""Server-side reconstruction of trusted execution context."""

from typing import Protocol

from tactiqo.shared.domain.execution import ExecutionContext


class ExecutionContextResolver(Protocol):
    """Resolve an opaque session into current effective access."""

    async def resolve(self, opaque_session: str, correlation_id: str) -> ExecutionContext | None:
        """Return current context or None without revealing failure details."""

    async def resolve_delegated(
        self,
        actor_id: str,
        organization_id: str,
        correlation_id: str,
        session_assurance: str,
    ) -> ExecutionContext | None:
        """Rebuild current authority for trusted signed internal delegation."""
