"""Per-request composition of tenant-visible MCP connections."""

from typing import Any

from tactiqo.integrations.application.ports import (
    ConnectionCredentialResolver,
    CredentialCipher,
    IntegrationConnectionRepository,
)
from tactiqo.integrations.application.service import ConnectionGatewayFactory
from tactiqo.integrations.domain.models import (
    ConnectionToolGrant,
    IntegrationConnection,
    ToolPermission,
)
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.application.policy import ToolPolicy
from tactiqo.tools.application.ports import ToolGateway
from tactiqo.tools.domain.models import ToolDefinition, ToolResult, ToolRisk
from tactiqo.tools.infrastructure.mcp_gateway import CompositeMcpToolGateway, McpToolGateway


class McpConnectionGatewayFactory:
    """Build bounded MCP gateways from validated connection records."""

    def __init__(self, policy: ToolPolicy, timeout: float, max_result: int) -> None:
        """Configure shared transport limits and policy classification."""
        self._policy = policy
        self._timeout = timeout
        self._max_result = max_result

    def build(self, connection: IntegrationConnection, authorization: str) -> ToolGateway:
        """Create one provider adapter using decrypted authorization in memory only."""
        return McpToolGateway(
            connection.endpoint_url,
            self._policy,
            self._timeout,
            self._max_result,
            server_label=connection.provider.value,
            headers={"Authorization": authorization},
        )


class TenantMcpToolGateway:
    """Resolve MCP connections using the current execution context on every call."""

    def __init__(
        self,
        repository: IntegrationConnectionRepository,
        cipher: CredentialCipher,
        factory: ConnectionGatewayFactory,
        static_gateways: dict[str, ToolGateway] | None = None,
        credential_resolver: ConnectionCredentialResolver | None = None,
    ) -> None:
        """Configure tenant resolution and optional development-only gateways."""
        self._repository = repository
        self._cipher = cipher
        self._factory = factory
        self._static_gateways = dict(static_gateways or {})
        self._credential_resolver = credential_resolver

    async def list_tools(self, context: ExecutionContext) -> list[ToolDefinition]:
        """Discover only tools from connections visible to this caller."""
        composite = await self._composite(context)
        return await composite.list_tools(context)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Resolve the caller's connections again before an approved invocation."""
        composite = await self._composite(context)
        return await composite.call_tool(name, arguments, context)

    async def _composite(self, context: ExecutionContext) -> CompositeMcpToolGateway:
        gateways = dict(self._static_gateways)
        for resolved in await self._repository.list_active(context):
            grants = await self._repository.effective_grants(resolved.connection.id, context)
            if not grants:
                continue
            label = f"{resolved.connection.provider.value}_{str(resolved.connection.id)[:8]}"
            authorization = (
                await self._credential_resolver.authorization_for(resolved, context)
                if self._credential_resolver is not None
                else self._cipher.decrypt(resolved.encrypted_authorization)
            )
            gateways[label] = GrantFilteredToolGateway(
                self._factory.build(resolved.connection, authorization), grants
            )
        return CompositeMcpToolGateway(gateways)


class GrantFilteredToolGateway:
    """Filter MCP definitions and calls using scoped effective grants."""

    def __init__(self, gateway: ToolGateway, grants: list[ConnectionToolGrant]) -> None:
        """Bind one provider gateway to an immutable effective grant snapshot."""
        self._gateway = gateway
        self._grants = tuple(grants)

    def _permissions(self, name: str) -> set[ToolPermission]:
        return {grant.permission for grant in self._grants if grant.tool_name in {"*", name}}

    async def list_tools(self, context: ExecutionContext) -> list[ToolDefinition]:
        """Hide ungranted definitions before they can enter model context."""
        tools = await self._gateway.list_tools(context)
        return [tool for tool in tools if self._permissions(tool.name)]

    async def call_tool(
        self, name: str, arguments: dict[str, Any], context: ExecutionContext
    ) -> ToolResult:
        """Recheck exact-tool permission before every provider call."""
        definition = next(
            (tool for tool in await self._gateway.list_tools(context) if tool.name == name), None
        )
        permissions = self._permissions(name)
        allowed = (
            bool(permissions)
            and definition is not None
            and (
                definition.risk is ToolRisk.READ_ONLY
                or bool(
                    {ToolPermission.EXECUTE, ToolPermission.ADMINISTER}.intersection(permissions)
                )
            )
        )
        if not allowed:
            return ToolResult(
                call_id="",
                name=name,
                content="Tool access denied by current organization policy.",
                is_error=True,
            )
        return await self._gateway.call_tool(name, arguments, context)
