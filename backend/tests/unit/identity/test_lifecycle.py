"""Four-eyes lifecycle authorization tests."""

from uuid import UUID, uuid4

import pytest

from tactiqo.identity.application.administration import AdministrationDeniedError
from tactiqo.identity.application.lifecycle import (
    LifecycleRequest,
    TenantLifecycleAction,
    TenantLifecycleService,
    TenantProvisionInput,
)
from tactiqo.shared.domain.execution import ExecutionContext


class FakeLifecycleRepository:
    """Capture lifecycle writes without persistence."""

    def __init__(self) -> None:
        """Initialize call captures."""
        self.created: list[tuple[str, TenantLifecycleAction, UUID, UUID | None, int | None]] = []
        self.approved: list[tuple[str, UUID, UUID]] = []
        self.provisioned: list[tuple[TenantProvisionInput, UUID]] = []

    async def provision(self, command: TenantProvisionInput, provisioned_by: UUID) -> None:
        """Capture platform provisioning."""
        self.provisioned.append((command, provisioned_by))

    async def create_request(
        self,
        organization_id: str,
        action: TenantLifecycleAction,
        requested_by: UUID,
        target_user_id: UUID | None,
        retention_days: int | None,
    ) -> LifecycleRequest:
        """Capture request creation."""
        self.created.append((organization_id, action, requested_by, target_user_id, retention_days))
        return LifecycleRequest(uuid4(), action.value, "pending")

    async def approve_request(
        self, organization_id: str, request_id: UUID, approved_by: UUID
    ) -> LifecycleRequest | None:
        """Capture request approval."""
        self.approved.append((organization_id, request_id, approved_by))
        return LifecycleRequest(request_id, "suspend", "approved")


def _context(actor: UUID, role: str, assurance: str = "step_up") -> ExecutionContext:
    return ExecutionContext(
        actor_id=str(actor),
        organization_id="org-a",
        correlation_id="correlation",
        classification_clearance="restricted",
        policy_version="v1",
        role_codes=(role,),
        session_assurance=assurance,
    )


@pytest.mark.anyio
async def test_only_step_up_owner_can_request_lifecycle_change() -> None:
    """Employees and non-step-up Owners cannot start high-risk transitions."""
    service = TenantLifecycleService(FakeLifecycleRepository())
    with pytest.raises(AdministrationDeniedError):
        await service.request(_context(uuid4(), "employee"), TenantLifecycleAction.SUSPEND)
    with pytest.raises(AdministrationDeniedError):
        await service.request(_context(uuid4(), "owner", "standard"), TenantLifecycleAction.SUSPEND)


@pytest.mark.anyio
async def test_owner_transfer_rejects_self_and_requires_target() -> None:
    """Ownership cannot be transferred to the initiating Owner."""
    actor = uuid4()
    service = TenantLifecycleService(FakeLifecycleRepository())
    with pytest.raises(AdministrationDeniedError):
        await service.request(
            _context(actor, "owner"),
            TenantLifecycleAction.OWNER_TRANSFER,
            actor,
        )


@pytest.mark.anyio
async def test_delete_requires_bounded_retention() -> None:
    """Safe deletion always has a bounded retention window."""
    service = TenantLifecycleService(FakeLifecycleRepository())
    with pytest.raises(AdministrationDeniedError):
        await service.request(_context(uuid4(), "owner"), TenantLifecycleAction.DELETE)


@pytest.mark.anyio
async def test_admin_approval_uses_server_tenant() -> None:
    """A step-up organization admin can provide the second decision."""
    repository = FakeLifecycleRepository()
    request_id = uuid4()
    await TenantLifecycleService(repository).approve(
        _context(uuid4(), "organization_admin"), request_id
    )
    assert repository.approved[0][0] == "org-a"


@pytest.mark.anyio
async def test_provision_requires_step_up_platform_administrator() -> None:
    """Organization Owners cannot provision unrelated SaaS tenants."""
    repository = FakeLifecycleRepository()
    command = TenantProvisionInput(
        "org-new", "org-new", "New Org", "oidc", "immutable-subject", "Owner"
    )
    with pytest.raises(AdministrationDeniedError):
        await TenantLifecycleService(repository).provision(_context(uuid4(), "owner"), command)
    actor = uuid4()
    await TenantLifecycleService(repository).provision(_context(actor, "platform_admin"), command)
    assert repository.provisioned == [(command, actor)]
