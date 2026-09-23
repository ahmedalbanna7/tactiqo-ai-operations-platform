"""Ports for tenant integration persistence and credential protection."""

from typing import Protocol
from uuid import UUID

from tactiqo.integrations.domain.models import (
    ConnectionScope,
    ConnectionStatus,
    ConnectionToolGrant,
    GrantSubjectType,
    IntegrationConnection,
    IntegrationProvider,
    ResolvedConnection,
    ToolPermission,
)
from tactiqo.shared.domain.execution import ExecutionContext


class ConnectionCredentialResolver(Protocol):
    """Resolve an authorization header, refreshing OAuth tokens when required."""

    async def authorization_for(
        self, resolved: ResolvedConnection, context: ExecutionContext
    ) -> str:
        """Return a short-lived authorization header for one visible connection."""


class CredentialCipher(Protocol):
    """Authenticated encryption boundary for provider authorization material."""

    def encrypt(self, plaintext: str) -> str:
        """Encrypt one secret value."""

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt one secret value or fail closed."""


class IntegrationConnectionRepository(Protocol):
    """Tenant-filtered connection persistence contract."""

    async def create(  # noqa: PLR0913 - explicit persistence contract
        self,
        *,
        provider: IntegrationProvider,
        name: str,
        endpoint_url: str,
        scope: ConnectionScope,
        encrypted_authorization: str,
        context: ExecutionContext,
    ) -> IntegrationConnection:
        """Create a connection in the caller's organization."""

    async def list_visible(self, context: ExecutionContext) -> list[IntegrationConnection]:
        """List organization connections and actor-owned personal connections."""

    async def list_active(self, context: ExecutionContext) -> list[ResolvedConnection]:
        """Resolve active connections after tenant and owner predicates."""

    async def get_active(
        self,
        connection_id: UUID,
        context: ExecutionContext,
    ) -> ResolvedConnection | None:
        """Return one visible active connection without leaking existence."""

    async def disable(
        self,
        connection_id: UUID,
        context: ExecutionContext,
    ) -> IntegrationConnection | None:
        """Disable one visible connection and remove it from tool resolution."""

    async def replace_credential(
        self,
        connection_id: UUID,
        encrypted_authorization: str,
        context: ExecutionContext,
    ) -> bool:
        """Atomically replace a visible active connection credential."""

    async def mark_status(
        self, connection_id: UUID, status: ConnectionStatus, context: ExecutionContext
    ) -> IntegrationConnection | None:
        """Move a visible connection to an explicit non-secret lifecycle state."""

    async def upsert_grant(  # noqa: PLR0913 - explicit policy coordinates
        self,
        connection_id: UUID,
        *,
        subject_type: GrantSubjectType,
        subject_id: str,
        tool_name: str,
        permission: ToolPermission,
        context: ExecutionContext,
    ) -> ConnectionToolGrant | None:
        """Create or narrow one explicit grant inside the caller tenant."""

    async def list_grants(
        self, connection_id: UUID, context: ExecutionContext
    ) -> list[ConnectionToolGrant]:
        """List grants only for a visible connection."""

    async def effective_grants(
        self, connection_id: UUID, context: ExecutionContext
    ) -> list[ConnectionToolGrant]:
        """Return grants matching current server-derived subject membership."""


class EffectiveToolAccessRepository(Protocol):
    """Narrow read-only port for a bounded subject access summary."""

    async def list_active_metadata(
        self, context: ExecutionContext, limit: int
    ) -> list[IntegrationConnection]:
        """List active visible connection metadata only, never credential columns."""

    async def effective_grants(
        self, connection_id: UUID, context: ExecutionContext
    ) -> list[ConnectionToolGrant]:
        """Return grants matching current server-derived subject membership."""
