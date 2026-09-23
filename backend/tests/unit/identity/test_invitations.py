"""Organization invitation links stay tenant-scoped and require admin authority."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from tactiqo.identity.application.administration import AdministrationDeniedError
from tactiqo.identity.application.invitations import (
    InvitationAdminView,
    InvitationView,
    OrganizationInvitationService,
)
from tactiqo.shared.domain.execution import ExecutionContext


class InvitationRepository:
    """Capture safe repository inputs for service policy tests."""

    def __init__(self) -> None:
        """Initialize write capture."""
        self.created: tuple[str, UUID, str, UUID, datetime] | None = None

    async def create(
        self, organization_id: str, department_id: UUID, token_hash: str,
        invited_by: UUID, expires_at: datetime,
    ) -> UUID:
        """Capture persisted data and return an identifier."""
        self.created = (organization_id, department_id, token_hash, invited_by, expires_at)
        return uuid4()

    async def inspect(self, _token_hash: str) -> InvitationView | None:
        """No public lookup is used in these service tests."""
        return None

    async def list_for_organization(self, _organization_id: str) -> list[InvitationAdminView]:
        """Return an empty bounded invitation list."""
        return []

    async def revoke(self, _organization_id: str, _invitation_id: UUID) -> bool:
        """Capture-free successful revocation response."""
        return True


def _context(role: str) -> ExecutionContext:
    return ExecutionContext(
        "00000000-0000-4000-8000-000000000001",
        "tenant-a",
        "corr",
        "internal",
        "1",
        role_codes=(role,),
    )


@pytest.mark.anyio
async def test_owner_gets_one_time_token_and_repository_only_receives_digest() -> None:
    """The raw token is returned once while only its digest reaches persistence."""
    repository = InvitationRepository()
    actor = UUID(_context("owner").actor_id)
    department = uuid4()
    created = await OrganizationInvitationService(repository).create(_context("owner"), department)
    assert created.token
    assert created.department_id == department
    assert repository.created is not None
    assert repository.created[0] == "tenant-a"
    assert repository.created[1] == department
    assert repository.created[2] != created.token
    assert repository.created[3] == actor
    assert timedelta(hours=71) < created.expires_at - datetime.now(UTC) <= timedelta(hours=72)


@pytest.mark.anyio
async def test_employee_cannot_create_or_enumerate_invites() -> None:
    """Unprivileged users cannot mint or enumerate tenant invitations."""
    repository = InvitationRepository()
    service = OrganizationInvitationService(repository)
    with pytest.raises(AdministrationDeniedError):
        await service.create(_context("employee"), uuid4())
    with pytest.raises(AdministrationDeniedError):
        await service.list(_context("employee"))
    assert repository.created is None
