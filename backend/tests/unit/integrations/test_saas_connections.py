"""Security tests for tenant integration primitives."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from tactiqo.integrations.application.service import (
    IntegrationAdministrationDeniedError,
    IntegrationConnectionService,
)
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
from tactiqo.integrations.infrastructure.crypto import FernetCredentialCipher
from tactiqo.integrations.infrastructure.gateway import (
    GrantFilteredToolGateway,
    TenantMcpToolGateway,
)
from tactiqo.integrations.infrastructure.oauth import (
    OAuthClient,
    OAuthCredentialResolver,
    OAuthFlowCoordinator,
    OAuthFlowError,
)
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.tools.domain.models import ToolDefinition, ToolResult, ToolRisk


class IdentityCipher:
    """Non-secret test cipher."""

    def encrypt(self, plaintext: str) -> str:
        """Return the test value unchanged."""
        return plaintext

    def decrypt(self, ciphertext: str) -> str:
        """Return the test value unchanged."""
        return ciphertext


class FakeGateway:
    """One-tool provider double."""

    async def list_tools(self, context: ExecutionContext) -> list[ToolDefinition]:
        """Expose one read-only tool."""
        del context
        return [ToolDefinition("read", "", {"type": "object"}, ToolRisk.READ_ONLY, "test")]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Return a deterministic result."""
        del arguments, context
        return ToolResult(call_id="", name=name, content="ok", is_error=False)


class FakeFactory:
    """Gateway factory double."""

    def build(self, connection: IntegrationConnection, authorization: str) -> FakeGateway:
        """Assert authorization is resolved only at the gateway boundary."""
        assert authorization == "Bearer secret"
        del connection
        return FakeGateway()


class FakeRepository:
    """Repository double that demonstrates context-bound resolution."""

    async def list_active(self, context: ExecutionContext) -> list[ResolvedConnection]:
        """Return a connection only to its organization."""
        if context.organization_id != "org-a":
            return []
        now = datetime.now(UTC)
        connection = IntegrationConnection(
            uuid4(),
            IntegrationProvider.JIRA,
            "jira-main",
            "https://mcp.atlassian.com/v2/mcp",
            ConnectionScope.ORGANIZATION,
            ConnectionStatus.ACTIVE,
            "org-a",
            None,
            "owner",
            now,
            now,
        )
        return [ResolvedConnection(connection, "Bearer secret")]

    async def create(self, **kwargs: object) -> IntegrationConnection:
        """Not used in this test."""
        del kwargs
        raise NotImplementedError

    async def list_visible(self, context: ExecutionContext) -> list[IntegrationConnection]:
        """Not used in this test."""
        del context
        raise NotImplementedError

    async def get_active(
        self, connection_id: UUID, context: ExecutionContext
    ) -> ResolvedConnection | None:
        """Not used in this test."""
        del connection_id, context
        raise NotImplementedError

    async def disable(
        self, connection_id: UUID, context: ExecutionContext
    ) -> IntegrationConnection | None:
        """Not used in this test."""
        del connection_id, context
        raise NotImplementedError

    async def replace_credential(
        self,
        connection_id: UUID,
        encrypted_authorization: str,
        context: ExecutionContext,
    ) -> bool:
        """Not used in this test."""
        del connection_id, encrypted_authorization, context
        raise NotImplementedError

    async def mark_status(
        self, connection_id: UUID, status: ConnectionStatus, context: ExecutionContext
    ) -> IntegrationConnection | None:
        """Not used in this test double."""
        del connection_id, status, context
        raise NotImplementedError

    async def effective_grants(
        self, connection_id: UUID, context: ExecutionContext
    ) -> list[ConnectionToolGrant]:
        """Grant the fake read tool only in its test tenant."""
        if context.organization_id != "org-a":
            return []
        now = datetime.now(UTC)
        return [
            ConnectionToolGrant(
                uuid4(),
                connection_id,
                "org-a",
                GrantSubjectType.ORGANIZATION,
                "org-a",
                "read",
                ToolPermission.READ,
                "owner",
                now,
            )
        ]

    async def upsert_grant(  # noqa: PLR0913 - mirror the explicit repository contract
        self,
        connection_id: UUID,
        *,
        subject_type: GrantSubjectType,
        subject_id: str,
        tool_name: str,
        permission: ToolPermission,
        context: ExecutionContext,
    ) -> ConnectionToolGrant | None:
        """Not used in this test double."""
        del connection_id, subject_type, subject_id, tool_name, permission, context
        raise NotImplementedError

    async def list_grants(
        self, connection_id: UUID, context: ExecutionContext
    ) -> list[ConnectionToolGrant]:
        """Not used in this test double."""
        del connection_id, context
        raise NotImplementedError


def test_fernet_cipher_rejects_tampering() -> None:
    """Provider credentials are encrypted and authenticated."""
    cipher = FernetCredentialCipher(Fernet.generate_key().decode())
    encrypted = cipher.encrypt("Bearer customer-token")

    assert "customer-token" not in encrypted
    assert cipher.decrypt(encrypted) == "Bearer customer-token"
    with pytest.raises(ValueError, match="failed authentication"):
        cipher.decrypt(encrypted[:-2] + "AA")


def test_gateway_discovery_is_tenant_scoped() -> None:
    """A tenant cannot discover another tenant's tools."""
    gateway = TenantMcpToolGateway(FakeRepository(), IdentityCipher(), FakeFactory())
    context_a = ExecutionContext("actor", "org-a", "c1", "internal", "test")
    context_b = ExecutionContext("actor", "org-b", "c2", "internal", "test")

    tools_a = asyncio.run(gateway.list_tools(context_a))
    tools_b = asyncio.run(gateway.list_tools(context_b))

    assert len(tools_a) == 1
    assert tools_a[0].name.startswith("jira_")
    assert tools_b == []


def test_exact_tool_grant_hides_every_other_definition_and_call() -> None:
    """A grant for one tool cannot expose or invoke another read-only tool."""
    now = datetime.now(UTC)
    grant = ConnectionToolGrant(
        uuid4(),
        uuid4(),
        "org-a",
        GrantSubjectType.USER,
        "actor",
        "different_tool",
        ToolPermission.READ,
        "owner",
        now,
    )
    gateway = GrantFilteredToolGateway(FakeGateway(), [grant])
    context = ExecutionContext("actor", "org-a", "c1", "internal", "test")

    assert asyncio.run(gateway.list_tools(context)) == []
    denied = asyncio.run(gateway.call_tool("read", {}, context))
    assert denied.is_error
    assert denied.content == "Tool access denied by current organization policy."


def test_read_grant_cannot_invoke_mutating_tool() -> None:
    """Visibility or read capability never implies side-effect permission."""

    class MutatingGateway(FakeGateway):
        async def list_tools(self, context: ExecutionContext) -> list[ToolDefinition]:
            del context
            return [ToolDefinition("write", "", {"type": "object"}, ToolRisk.MUTATING, "test")]

    now = datetime.now(UTC)
    grant = ConnectionToolGrant(
        uuid4(),
        uuid4(),
        "org-a",
        GrantSubjectType.USER,
        "actor",
        "write",
        ToolPermission.READ,
        "owner",
        now,
    )
    gateway = GrantFilteredToolGateway(MutatingGateway(), [grant])
    context = ExecutionContext("actor", "org-a", "c1", "internal", "test")

    assert [tool.name for tool in asyncio.run(gateway.list_tools(context))] == ["write"]
    assert asyncio.run(gateway.call_tool("write", {}, context)).is_error


def test_employee_cannot_create_organization_connection() -> None:
    """A shared connection requires an owner-assigned integration manager role."""
    service = IntegrationConnectionService(FakeRepository(), IdentityCipher(), FakeFactory())
    employee = ExecutionContext(
        "actor", "org-a", "c1", "internal", "test", role_codes=("employee",)
    )

    with pytest.raises(IntegrationAdministrationDeniedError):
        asyncio.run(
            service.create(
                provider=IntegrationProvider.JIRA,
                name="shared",
                endpoint_url="https://mcp.atlassian.com/v2/mcp",
                authorization="Bearer secret",
                scope=ConnectionScope.ORGANIZATION,
                context=employee,
            )
        )


def test_employee_can_create_only_their_personal_connection() -> None:
    """Personal integration onboarding remains actor-owned and tenant-scoped."""
    now = datetime.now(UTC)

    class CreatingRepository(FakeRepository):
        async def create(self, **kwargs: object) -> IntegrationConnection:
            return IntegrationConnection(
                uuid4(),
                cast("IntegrationProvider", kwargs["provider"]),
                str(kwargs["name"]),
                str(kwargs["endpoint_url"]),
                cast("ConnectionScope", kwargs["scope"]),
                ConnectionStatus.ACTIVE,
                "org-a",
                "actor",
                "actor",
                now,
                now,
            )

    service = IntegrationConnectionService(CreatingRepository(), IdentityCipher(), FakeFactory())
    employee = ExecutionContext(
        "actor", "org-a", "c1", "internal", "test", role_codes=("employee",)
    )
    connection = asyncio.run(
        service.create(
            provider=IntegrationProvider.SLACK,
            name="mine",
            endpoint_url="https://mcp.slack.com/mcp",
            authorization="Bearer secret",
            scope=ConnectionScope.PERSONAL,
            context=employee,
        )
    )

    assert connection.owner_actor_id == "actor"


class FakeConnectionService:
    """Capture OAuth completion without persistence."""

    @staticmethod
    def require_manager(scope: ConnectionScope, context: ExecutionContext) -> None:
        """Accept personal test flows; production policy is tested separately."""
        del scope, context

    async def create(self, **kwargs: object) -> IntegrationConnection:
        """Return the connection supplied by the coordinator."""
        now = datetime.now(UTC)
        return IntegrationConnection(
            uuid4(),
            kwargs["provider"],  # type: ignore[arg-type]
            str(kwargs["name"]),
            str(kwargs["endpoint_url"]),
            kwargs["scope"],  # type: ignore[arg-type]
            ConnectionStatus.ACTIVE,
            "org-a",
            "actor" if kwargs["scope"] is ConnectionScope.PERSONAL else None,
            "actor",
            now,
            now,
        )


def test_oauth_state_is_pkce_protected_and_tenant_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    """OAuth state cannot be reused by a different tenant context."""
    coordinator = OAuthFlowCoordinator(
        FakeConnectionService(),  # type: ignore[arg-type]
        Fernet.generate_key().decode(),
        "http://127.0.0.1:18000",
        "http://127.0.0.1:13000",
        "slack-client",
        "slack-secret",
        5,
    )

    async def fake_client(provider: IntegrationProvider, callback: str) -> OAuthClient:
        del provider, callback
        return OAuthClient(
            "client",
            "secret",
            "https://provider.test/authorize",
            "https://provider.test/token",
            "read",
        )

    monkeypatch.setattr(coordinator, "_client", fake_client)
    context = ExecutionContext("actor", "org-a", "c1", "internal", "test")
    started = asyncio.run(
        coordinator.start(IntegrationProvider.JIRA, "Jira main", ConnectionScope.PERSONAL, context)
    )
    query = parse_qs(urlsplit(started.authorization_url).query)

    assert query["code_challenge_method"] == ["S256"]
    assert query["state"]
    wrong_tenant = ExecutionContext("actor", "org-b", "c2", "internal", "test")
    with pytest.raises(OAuthFlowError, match="tenant session"):
        asyncio.run(
            coordinator.callback(
                IntegrationProvider.JIRA, "unused-code", query["state"][0], wrong_tenant
            )
        )


def test_oauth_resolver_returns_bearer_for_fresh_token() -> None:
    """OAuth material is converted to a bearer header only at the gateway boundary."""
    now = datetime.now(UTC)
    connection = IntegrationConnection(
        uuid4(),
        IntegrationProvider.SLACK,
        "slack-main",
        "https://mcp.slack.com/mcp",
        ConnectionScope.ORGANIZATION,
        ConnectionStatus.ACTIVE,
        "org-a",
        None,
        "actor",
        now,
        now,
    )
    material = json.dumps(
        {
            "kind": "oauth",
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "expires_at": "2999-01-01T00:00:00+00:00",
            "token_endpoint": "https://provider.test/token",
            "client_id": "client",
            "client_secret": "secret",
        }
    )
    resolver = OAuthCredentialResolver(FakeRepository(), IdentityCipher(), 5)
    header = asyncio.run(
        resolver.authorization_for(
            ResolvedConnection(connection, material),
            ExecutionContext("actor", "org-a", "c1", "internal", "test"),
        )
    )

    assert header == "Bearer access-secret"
