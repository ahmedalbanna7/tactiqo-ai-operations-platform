"""Agent Catalog administration policy tests."""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from tactiqo.agents.catalog.application.administration import (
    AgentApprovalChainInput,
    AgentCatalogAdministrationService,
)
from tactiqo.authorization.domain.models import PolicyAction
from tactiqo.identity.application.administration import AdministrationDeniedError
from tactiqo.shared.domain.execution import ExecutionContext


class ApprovalChainRepository:
    """Capture approval-chain writes after application authorization."""

    def __init__(self) -> None:
        """Initialize an empty call capture."""
        self.calls: list[tuple[str, AgentApprovalChainInput, UUID]] = []

    async def set_approval_chain(
        self, organization_id: str, command: AgentApprovalChainInput, actor_id: UUID
    ) -> UUID:
        """Record the server-scoped write and return its identifier."""
        self.calls.append((organization_id, command, actor_id))
        return uuid4()


def _context(actor: UUID, role: str) -> ExecutionContext:
    return ExecutionContext(
        str(actor),
        "org-a",
        "correlation",
        "restricted",
        "v1",
        role_codes=(role,),
    )


def _command(*steps: str) -> AgentApprovalChainInput:
    return AgentApprovalChainInput(
        "planner",
        PolicyAction.EXECUTE,
        "high",
        "jira",
        steps,
    )


@pytest.mark.anyio
async def test_owner_sets_chain_in_server_derived_tenant() -> None:
    """Tenant and actor are sourced from the immutable execution context."""
    actor = uuid4()
    repository = ApprovalChainRepository()
    await AgentCatalogAdministrationService(repository).set_approval_chain(
        _context(actor, "owner"), _command("department_manager", "organization_owner")
    )
    assert repository.calls[0][0] == "org-a"
    assert repository.calls[0][2] == actor


@pytest.mark.anyio
async def test_employee_and_empty_chain_are_denied_before_write() -> None:
    """Only administrators may store a valid, non-empty ordered chain."""
    repository = ApprovalChainRepository()
    service = AgentCatalogAdministrationService(repository)
    with pytest.raises(AdministrationDeniedError):
        await service.set_approval_chain(_context(uuid4(), "employee"), _command("owner"))
    with pytest.raises(AdministrationDeniedError):
        await service.set_approval_chain(_context(uuid4(), "owner"), _command())
    assert repository.calls == []


@pytest.mark.anyio
async def test_assignment_directory_is_admin_only_and_tenant_scoped() -> None:
    """An employee cannot enumerate assignments even by calling the API directly."""
    repository = AsyncMock()
    repository.list_assignments.return_value = []
    service = AgentCatalogAdministrationService(repository)
    with pytest.raises(AdministrationDeniedError):
        await service.list_assignments(_context(uuid4(), "employee"))
    repository.list_assignments.assert_not_awaited()
    assert await service.list_assignments(_context(uuid4(), "owner")) == []
    repository.list_assignments.assert_awaited_once_with("org-a")


@pytest.mark.anyio
async def test_catalog_directory_is_admin_only_and_tenant_scoped() -> None:
    """Catalog versions are not enumerable to employees; tenant ID is server-derived."""
    repository = AsyncMock()
    repository.list_catalog.return_value = []
    service = AgentCatalogAdministrationService(repository)
    with pytest.raises(AdministrationDeniedError):
        await service.list_catalog(_context(uuid4(), "employee"))
    repository.list_catalog.assert_not_awaited()
    assert await service.list_catalog(_context(uuid4(), "owner")) == []
    repository.list_catalog.assert_awaited_once_with("org-a")
