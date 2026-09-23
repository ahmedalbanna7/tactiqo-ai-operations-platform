"""Use cases for SaaS-managed Jira and Slack connections."""

from collections.abc import Sequence
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from tactiqo.integrations.application.ports import (
    ConnectionCredentialResolver,
    CredentialCipher,
    IntegrationConnectionRepository,
)
from tactiqo.integrations.domain.models import (
    ConnectionScope,
    ConnectionStatus,
    ConnectionToolGrant,
    GrantSubjectType,
    IntegrationConnection,
    IntegrationProvider,
    ToolPermission,
)
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.application.ports import ToolGateway

_ALLOWED_HOSTS = {
    IntegrationProvider.JIRA: frozenset({"mcp.atlassian.com"}),
    IntegrationProvider.SLACK: frozenset({"mcp.slack.com"}),
}
_INTEGRATION_MANAGER_ROLES = frozenset(
    {"owner", "organization_admin", "integration_manager", "platform_admin"}
)
_MAX_TOOL_NAME = 160


class IntegrationAdministrationDeniedError(PermissionError):
    """Caller is not assigned to administer organization integrations."""


class ConnectionGatewayFactory(Protocol):
    """Build a provider gateway without exposing transport details to use cases."""

    def build(self, connection: IntegrationConnection, authorization: str) -> ToolGateway:
        """Build one bounded MCP gateway."""


class IntegrationConnectionService:
    """Manage secret-safe, tenant-scoped provider connections."""

    def __init__(
        self,
        repository: IntegrationConnectionRepository,
        cipher: CredentialCipher,
        gateway_factory: ConnectionGatewayFactory,
        credential_resolver: ConnectionCredentialResolver | None = None,
    ) -> None:
        """Configure persistence, encryption and verification boundaries."""
        self._repository = repository
        self._cipher = cipher
        self._gateway_factory = gateway_factory
        self._credential_resolver = credential_resolver

    async def create(  # noqa: PLR0913 - explicit connection input contract
        self,
        *,
        provider: IntegrationProvider,
        name: str,
        endpoint_url: str,
        authorization: str,
        scope: ConnectionScope,
        context: ExecutionContext,
    ) -> IntegrationConnection:
        """Validate and encrypt a new connection before persistence."""
        self.require_manager(scope, context)
        self._validate_endpoint(provider, endpoint_url)
        if not authorization.strip():
            msg = "Provider authorization cannot be empty."
            raise ValueError(msg)
        return await self._repository.create(
            provider=provider,
            name=name.strip(),
            endpoint_url=endpoint_url,
            scope=scope,
            encrypted_authorization=self._cipher.encrypt(authorization.strip()),
            context=context,
        )

    async def list(self, context: ExecutionContext) -> list[IntegrationConnection]:
        """Return visible secret-free connections."""
        return await self._repository.list_visible(context)

    async def disable(
        self,
        connection_id: UUID,
        context: ExecutionContext,
    ) -> IntegrationConnection | None:
        """Disable a visible connection."""
        existing = next(
            (
                item
                for item in await self._repository.list_visible(context)
                if item.id == connection_id
            ),
            None,
        )
        if existing is None:
            return None
        self.require_manager(existing.scope, context)
        return await self._repository.disable(connection_id, context)

    async def verify(self, connection_id: UUID, context: ExecutionContext) -> int | None:
        """Discover tools with one visible connection and return their count."""
        resolved = await self._repository.get_active(connection_id, context)
        if resolved is None:
            return None
        self.require_manager(resolved.connection.scope, context)
        authorization = (
            await self._credential_resolver.authorization_for(resolved, context)
            if self._credential_resolver is not None
            else self._cipher.decrypt(resolved.encrypted_authorization)
        )
        gateway = self._gateway_factory.build(resolved.connection, authorization)
        return len(await gateway.list_tools(context))

    async def set_grant(  # noqa: PLR0913 - explicit policy coordinates
        self,
        connection_id: UUID,
        *,
        subject_type: GrantSubjectType,
        subject_id: str,
        tool_name: str,
        permission: ToolPermission,
        context: ExecutionContext,
    ) -> ConnectionToolGrant | None:
        """Assign one explicit capability after manager and scope validation."""
        connection = next(
            (
                item
                for item in await self._repository.list_visible(context)
                if item.id == connection_id
            ),
            None,
        )
        if connection is None:
            return None
        self.require_manager(connection.scope, context)
        if subject_type is GrantSubjectType.ORGANIZATION and subject_id != context.organization_id:
            message = "Organization grant subject must match the current tenant."
            raise ValueError(message)
        if connection.scope is ConnectionScope.PERSONAL and not (
            subject_type is GrantSubjectType.USER and subject_id == context.actor_id
        ):
            message = "Personal connections can be granted only to their owner."
            raise ValueError(message)
        normalized_tool = tool_name.strip()
        if not normalized_tool or len(normalized_tool) > _MAX_TOOL_NAME:
            message = "Tool name is invalid."
            raise ValueError(message)
        return await self._repository.upsert_grant(
            connection_id,
            subject_type=subject_type,
            subject_id=subject_id.strip(),
            tool_name=normalized_tool,
            permission=permission,
            context=context,
        )

    async def list_grants(
        self, connection_id: UUID, context: ExecutionContext
    ) -> Sequence[ConnectionToolGrant] | None:
        """Return grant policy only to a manager of the visible connection."""
        connection = next(
            (
                item
                for item in await self._repository.list_visible(context)
                if item.id == connection_id
            ),
            None,
        )
        if connection is None:
            return None
        self.require_manager(connection.scope, context)
        return await self._repository.list_grants(connection_id, context)

    async def reconnect(
        self, connection_id: UUID, authorization: str, context: ExecutionContext
    ) -> IntegrationConnection | None:
        """Rotate credentials and reactivate a visible connection."""
        connection = next(
            (
                item
                for item in await self._repository.list_visible(context)
                if item.id == connection_id
            ),
            None,
        )
        if connection is None:
            return None
        self.require_manager(connection.scope, context)
        if not authorization.strip():
            message = "Provider authorization cannot be empty."
            raise ValueError(message)
        updated = await self._repository.replace_credential(
            connection_id, self._cipher.encrypt(authorization.strip()), context
        )
        if not updated:
            return None
        return next(
            (
                item
                for item in await self._repository.list_visible(context)
                if item.id == connection_id
            ),
            None,
        )

    async def revoke(
        self, connection_id: UUID, context: ExecutionContext
    ) -> IntegrationConnection | None:
        """Revoke platform use immediately and erase stored credentials."""
        connection = next(
            (
                item
                for item in await self._repository.list_visible(context)
                if item.id == connection_id
            ),
            None,
        )
        if connection is None:
            return None
        self.require_manager(connection.scope, context)
        return await self._repository.mark_status(connection_id, ConnectionStatus.REVOKED, context)

    @staticmethod
    def require_manager(scope: ConnectionScope, context: ExecutionContext) -> None:
        """Protect shared connections while allowing users to own personal connections."""
        if scope is ConnectionScope.ORGANIZATION and not _INTEGRATION_MANAGER_ROLES.intersection(
            context.role_codes
        ):
            message = "Organization integration management requires an assigned manager."
            raise IntegrationAdministrationDeniedError(message)

    @staticmethod
    def _validate_endpoint(provider: IntegrationProvider, endpoint_url: str) -> None:
        parsed = urlsplit(endpoint_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS[provider]:
            msg = f"Unsupported {provider.value} MCP endpoint."
            raise ValueError(msg)
