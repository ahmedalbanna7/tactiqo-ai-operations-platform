"""HTTP authorization boundaries for company-member access preview."""

from dataclasses import dataclass, field

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from tactiqo.agents.catalog.application.administration import AgentCatalogAdministrationService
from tactiqo.agents.catalog.application.service import AgentCatalogService
from tactiqo.agents.catalog.domain.models import EffectiveAgentCard
from tactiqo.authorization.application.preview import EffectiveAccessPreviewService
from tactiqo.identity.application.administration import OrganizationAdministrationService
from tactiqo.identity.application.invitations import OrganizationInvitationService
from tactiqo.integrations.application.service import IntegrationConnectionService
from tactiqo.knowledge.application.service import KnowledgeService
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.settings import RuntimeEnvironment, Settings
from tactiqo_api.factory import create_app


def _settings(*, local_context: bool) -> Settings:
    """Build an isolated test app without loading developer environment files."""
    return Settings(
        _env_file=None,
        app_name="Tactiqo Access Preview Test",
        app_version="test",
        environment=RuntimeEnvironment.TEST,
        database_url=SecretStr("postgresql+asyncpg://ignored"),
        redis_url=SecretStr("redis://ignored"),
        rabbitmq_url=SecretStr("amqp://ignored"),
        minio_endpoint="http://ignored",
        minio_access_key=SecretStr("ignored"),
        minio_secret_key=SecretStr("ignored"),
        local_development_context_enabled=local_context,
    )


@dataclass
class FakeContextResolver:
    """Record trusted context resolution calls for route-level assertions."""

    roles: tuple[str, ...] = ()
    contexts: list[tuple[str, str, str, str]] = field(default_factory=list)

    async def resolve_delegated(
        self, actor_id: str, organization_id: str, correlation_id: str, assurance: str
    ) -> ExecutionContext | None:
        """Return the configured context and record the server-resolved request."""
        self.contexts.append((actor_id, organization_id, correlation_id, assurance))
        return ExecutionContext(
            actor_id,
            organization_id,
            correlation_id,
            "internal",
            "test-policy",
            role_codes=self.roles,
        )

    async def resolve(self, opaque_session: str, correlation_id: str) -> ExecutionContext | None:
        """Do not resolve OIDC cookies in this local route test double."""
        del opaque_session, correlation_id
        return None


class NeverReadAgentCatalog(AgentCatalogService):
    """Fail if an unauthorized preview reaches data-dependent agent discovery."""

    def __init__(self) -> None:
        """Avoid configuring repository dependencies for a denial-only test double."""

    async def effective_cards(self, context: ExecutionContext) -> list[EffectiveAgentCard]:
        """Fail if a denied request crosses into catalog evaluation."""
        del context
        message = "unauthorized access preview must not enumerate agents"
        raise AssertionError(message)


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio only; the platform does not support multiple async runtimes."""
    return "asyncio"


@pytest.mark.anyio
async def test_access_preview_requires_authenticated_session() -> None:
    """Missing session is rejected before the preview service or target member is touched."""
    resolver = FakeContextResolver(roles=("owner",))
    app = create_app(_settings(local_context=False))
    app.state.identity_context_resolver = resolver
    app.state.effective_access_preview_service = EffectiveAccessPreviewService(
        resolver, NeverReadAgentCatalog()
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/company/people/10000000-0000-4000-8000-000000000001/access-preview",
            json={},
        )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert resolver.contexts == []
    assert "10000000-0000-4000-8000-000000000001" not in response.text


@pytest.mark.anyio
async def test_employee_cannot_probe_another_member_access_preview() -> None:
    """An authenticated employee gets a generic denial before target lookup or policy reads."""
    resolver = FakeContextResolver(roles=("employee",))
    app = create_app(_settings(local_context=True))
    app.state.identity_context_resolver = resolver
    app.state.effective_access_preview_service = EffectiveAccessPreviewService(
        resolver, NeverReadAgentCatalog()
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/company/people/10000000-0000-4000-8000-000000000001/access-preview",
            json={},
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Administration denied."}
    assert len(resolver.contexts) == 1
    assert resolver.contexts[0][0] == _settings(local_context=True).local_actor_id
    assert resolver.contexts[0][3] == "step_up"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/v1/company/units", None),
        ("GET", "/api/v1/company/people", None),
        (
            "POST",
            "/api/v1/company/departments",
            {"code": "ENG", "name": "Engineering"},
        ),
        (
            "POST",
            "/api/v1/company/teams",
            {
                "department_id": "10000000-0000-4000-8000-000000000002",
                "name": "Platform",
            },
        ),
        (
            "POST",
            "/api/v1/company/projects",
            {
                "department_id": "10000000-0000-4000-8000-000000000002",
                "code": "PRJ",
                "name": "Project",
            },
        ),
        (
            "POST",
            "/api/v1/company/department/10000000-0000-4000-8000-000000000002/members",
            {"user_id": "10000000-0000-4000-8000-000000000003"},
        ),
        (
            "POST",
            "/api/v1/company/roles",
            {
                "user_id": "10000000-0000-4000-8000-000000000003",
                "role": "organization_admin",
            },
        ),
        (
            "PUT",
            "/api/v1/company/people/10000000-0000-4000-8000-000000000003/status",
            {"status": "suspended"},
        ),
        (
            "GET",
            "/api/v1/company/people/10000000-0000-4000-8000-000000000003/roles",
            None,
        ),
        (
            "DELETE",
            "/api/v1/company/roles/10000000-0000-4000-8000-000000000004",
            None,
        ),
        ("GET", "/api/v1/company/invitations", None),
        (
            "POST",
            "/api/v1/company/invitations",
            {"department_id": "10000000-0000-4000-8000-000000000002"},
        ),
        ("GET", "/api/v1/agent-catalog/catalog", None),
        (
            "POST",
            "/api/v1/agent-catalog/install",
            {"agent_code": "project_manager", "version": "1"},
        ),
        (
            "PATCH",
            "/api/v1/agent-catalog/project_manager",
            {"enabled": True},
        ),
        ("GET", "/api/v1/agent-catalog/assignments", None),
        (
            "POST",
            "/api/v1/knowledge/documents/10000000-0000-4000-8000-000000000005/promote",
            {"confirmation_name": "private.pdf"},
        ),
        (
            "POST",
            "/api/v1/integrations/connections",
            {
                "provider": "jira",
                "name": "Company Jira",
                "endpoint_url": "https://mcp.atlassian.com/v1",
                "authorization": "test-secret",
                "scope": "organization",
            },
        ),
    ],
)
async def test_employee_is_denied_across_company_administration_routes(
    method: str, path: str, payload: dict[str, str] | None
) -> None:
    """Employee requests fail at the service guard before repository state is accessed."""
    resolver = FakeContextResolver(roles=("employee",))
    app = create_app(_settings(local_context=True))
    app.state.identity_context_resolver = resolver
    # The service guard must reject before touching its repository dependency.
    app.state.organization_administration_service = object.__new__(
        OrganizationAdministrationService
    )
    app.state.organization_invitation_service = object.__new__(OrganizationInvitationService)
    app.state.agent_catalog_administration_service = object.__new__(
        AgentCatalogAdministrationService
    )
    app.state.knowledge_service = object.__new__(KnowledgeService)
    app.state.integration_service = object.__new__(IntegrationConnectionService)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(method, path, json=payload)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Administration denied."}
    assert len(resolver.contexts) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/api/v1/company/roles",
            {
                "user_id": "10000000-0000-4000-8000-000000000003",
                "role": "organization_admin",
            },
        ),
        (
            "PUT",
            "/api/v1/company/people/10000000-0000-4000-8000-000000000003/status",
            {"status": "suspended"},
        ),
        (
            "DELETE",
            "/api/v1/company/roles/10000000-0000-4000-8000-000000000004",
            None,
        ),
    ],
)
async def test_organization_admin_cannot_call_owner_only_lifecycle_routes(
    method: str, path: str, payload: dict[str, str] | None
) -> None:
    """Step-up does not substitute for the Owner role on high-impact lifecycle APIs."""
    resolver = FakeContextResolver(roles=("organization_admin",))
    app = create_app(_settings(local_context=True))
    app.state.identity_context_resolver = resolver
    app.state.organization_administration_service = object.__new__(
        OrganizationAdministrationService
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(method, path, json=payload)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Administration denied."}
    assert resolver.contexts
    assert resolver.contexts[0][3] == "step_up"
