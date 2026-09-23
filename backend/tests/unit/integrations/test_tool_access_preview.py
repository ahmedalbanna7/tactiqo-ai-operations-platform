"""Secret-free and bounded tests for effective integration access summaries."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from tactiqo.integrations.domain.models import (
    ConnectionScope,
    ConnectionStatus,
    ConnectionToolGrant,
    GrantSubjectType,
    IntegrationConnection,
    IntegrationProvider,
    ToolPermission,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from tactiqo.integrations.application.ports import EffectiveToolAccessRepository


from tactiqo.integrations.infrastructure.repository import (
    SqlAlchemyIntegrationConnectionRepository,
)
from tactiqo.integrations.infrastructure.tool_access_preview import (
    MAX_PREVIEW_CONNECTIONS,
    MAX_PREVIEW_GRANTS,
    SqlEffectiveToolAccessReader,
)
from tactiqo.shared.domain.execution import ExecutionContext


def execution_context() -> ExecutionContext:
    """Construct a tenant member context with hierarchy-bound access."""
    return ExecutionContext(
        actor_id="employee-a",
        organization_id="tenant-a",
        correlation_id="preview-test",
        classification_clearance="internal",
        policy_version="policy-1",
        role_codes=("employee",),
        department_ids=("department-a",),
        session_assurance="standard",
    )


def connection(name: str) -> IntegrationConnection:
    """Make a safe public integration connection value."""
    now = datetime.now(UTC)
    return IntegrationConnection(
        uuid4(),
        IntegrationProvider.JIRA,
        name,
        "https://mcp.atlassian.com/v2/mcp",
        ConnectionScope.ORGANIZATION,
        ConnectionStatus.ACTIVE,
        "tenant-a",
        None,
        "owner-a",
        now,
        now,
    )


class PreviewRepository:
    """Minimal repository exposing metadata and effective grants only."""

    def __init__(self, connections: list[IntegrationConnection]) -> None:
        """Store active metadata fixtures."""
        self.connections = connections
        self.requested_limit: int | None = None
        self.grant_reads: list[UUID] = []

    async def list_active_metadata(
        self, context: ExecutionContext, limit: int
    ) -> list[IntegrationConnection]:
        """Capture the requested bound and return only public connection models."""
        assert context.organization_id == "tenant-a"
        self.requested_limit = limit
        return self.connections[:limit]

    async def effective_grants(
        self, connection_id: UUID, context: ExecutionContext
    ) -> list[ConnectionToolGrant]:
        """Return a sample exact grant scoped to the target department."""
        self.grant_reads.append(connection_id)
        return [
            ConnectionToolGrant(
                uuid4(),
                connection_id,
                context.organization_id,
                GrantSubjectType.DEPARTMENT,
                "department-a",
                "jira_search",
                ToolPermission.READ,
                "owner-a",
                datetime.now(UTC),
            )
        ]


@pytest.mark.anyio
async def test_reader_returns_effective_tool_grants_without_connection_secrets() -> None:
    """Summary includes only active grants and safe provider/connection/tool metadata."""
    repository = PreviewRepository([connection("jira-company")])
    reader = SqlEffectiveToolAccessReader(cast("EffectiveToolAccessRepository", repository))

    result, truncated = await reader.read(execution_context())

    assert truncated is False
    assert result[0].provider == "jira"
    assert result[0].connection_name == "jira-company"
    assert result[0].tool_name == "jira_search"
    assert result[0].permission == "read"
    assert not hasattr(result[0], "endpoint_url")
    assert not hasattr(result[0], "encrypted_authorization")
    assert repository.requested_limit == MAX_PREVIEW_CONNECTIONS + 1


@pytest.mark.anyio
async def test_reader_caps_connection_count_and_marks_truncated_results() -> None:
    """More than the bounded number of visible connections sets the truncation flag."""
    repository = PreviewRepository(
        [connection(f"connection-{index}") for index in range(MAX_PREVIEW_CONNECTIONS + 1)]
    )
    reader = SqlEffectiveToolAccessReader(cast("EffectiveToolAccessRepository", repository))

    result, truncated = await reader.read(execution_context())

    assert truncated is True
    assert len(result) == MAX_PREVIEW_CONNECTIONS
    assert len(repository.grant_reads) == MAX_PREVIEW_CONNECTIONS


@pytest.mark.anyio
async def test_reader_caps_effective_grant_response() -> None:
    """A large grant set is truncated without returning an oversized preview payload."""

    class ManyGrantRepository(PreviewRepository):
        async def effective_grants(
            self, connection_id: UUID, context: ExecutionContext
        ) -> list[ConnectionToolGrant]:
            del connection_id
            now = datetime.now(UTC)
            return [
                ConnectionToolGrant(
                    uuid4(), uuid4(), context.organization_id, GrantSubjectType.USER,
                    context.actor_id, f"tool-{index}", ToolPermission.READ, "owner-a", now,
                )
                for index in range(MAX_PREVIEW_GRANTS + 1)
            ]

    repository = ManyGrantRepository([connection("jira-company")])
    reader = SqlEffectiveToolAccessReader(cast("EffectiveToolAccessRepository", repository))

    result, truncated = await reader.read(execution_context())

    assert truncated is True
    assert len(result) == MAX_PREVIEW_GRANTS


@pytest.mark.anyio
async def test_metadata_query_does_not_select_encrypted_authorization() -> None:
    """The DB projection itself must not load the credential ciphertext into preview code."""
    session = AsyncMock()
    result = Mock()
    result.all.return_value = []
    session.execute.return_value = result
    session_manager = AsyncMock()
    session_manager.__aenter__.return_value = session
    sessions = Mock(return_value=session_manager)
    repository = SqlAlchemyIntegrationConnectionRepository(
        cast("async_sessionmaker[AsyncSession]", sessions)
    )

    await repository.list_active_metadata(execution_context(), 7)

    statement = str(session.execute.call_args.args[0]).lower()
    assert "encrypted_authorization" not in statement
    assert "organization_id" in statement
    assert "limit" in statement
