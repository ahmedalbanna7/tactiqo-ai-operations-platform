"""Organization administration policy tests."""

from uuid import UUID, uuid4

import pytest

from tactiqo.identity.application.administration import (
    AdministrationDeniedError,
    ChildUnitInput,
    DepartmentInput,
    MemberDetail,
    MembershipInput,
    OrganizationAdministrationService,
    UnitDetail,
    UnitRecord,
)
from tactiqo.identity.domain.models import OrganizationRole
from tactiqo.shared.domain.execution import ExecutionContext


class FakeRepository:
    """Capture authorized writes for policy tests."""

    def __init__(self) -> None:
        """Initialize empty persistence-call captures."""
        self.organizations: list[str] = []
        self.assignments: list[tuple[str, UUID, str, UUID]] = []
        self.memberships: list[tuple[str, str, UUID, UUID]] = []
        self.status_changes: list[tuple[str, UUID, str, UUID]] = []

    async def create_department(self, organization_id: str, command: DepartmentInput) -> UnitRecord:
        """Record exact tenant predicate."""
        self.organizations.append(organization_id)
        return UnitRecord(uuid4(), command.code, command.name)

    async def list_units(self, organization_id: str) -> list[UnitDetail]:
        """Return an empty tenant-scoped company structure for unused protocol methods."""
        _ = organization_id
        return []

    async def list_people(self, organization_id: str) -> list[MemberDetail]:
        """Return an empty tenant-scoped people directory for unused protocol methods."""
        _ = organization_id
        return []

    async def assign_role(
        self, organization_id: str, user_id: UUID, role_code: str, assigned_by: UUID
    ) -> None:
        """Record one assignment."""
        self.assignments.append((organization_id, user_id, role_code, assigned_by))

    async def set_member_status(
        self, organization_id: str, user_id: UUID, status: str, changed_by: UUID
    ) -> bool:
        """Capture lifecycle updates for service authorization assertions."""
        self.status_changes.append((organization_id, user_id, status, changed_by))
        return True

    async def list_role_history(
        self, organization_id: str, user_id: UUID
    ) -> list[dict[str, object]]:
        """Return a bounded, tenant-marked fake history row."""
        return [{"org": organization_id, "user": user_id}]

    async def revoke_role(
        self, organization_id: str, assignment_id: UUID, revoked_by: UUID
    ) -> bool:
        """Accept one test revocation without persisting mutable state."""
        _ = organization_id, assignment_id, revoked_by
        return True

    async def create_team(self, organization_id: str, command: ChildUnitInput) -> UnitRecord:
        """Capture a team write in the exact server tenant."""
        self.organizations.append(organization_id)
        return UnitRecord(uuid4(), command.code or "team", command.name)

    async def create_project(self, organization_id: str, command: ChildUnitInput) -> UnitRecord:
        """Capture a project write in the exact server tenant."""
        self.organizations.append(organization_id)
        return UnitRecord(uuid4(), command.code or "project", command.name)

    async def assign_membership(
        self,
        organization_id: str,
        kind: str,
        command: MembershipInput,
        assigned_by: UUID,
    ) -> None:
        """Capture a bounded hierarchy membership."""
        self.memberships.append((organization_id, kind, command.unit_id, assigned_by))


def _context(actor: UUID, *roles: str, assurance: str = "standard") -> ExecutionContext:
    return ExecutionContext(
        str(actor),
        "org-a",
        "correlation",
        "internal",
        "v1",
        role_codes=roles,
        session_assurance=assurance,
    )


@pytest.mark.anyio
async def test_employee_cannot_administer_company() -> None:
    """Employee denial occurs before repository access."""
    repository = FakeRepository()
    service = OrganizationAdministrationService(repository)
    with pytest.raises(AdministrationDeniedError):
        await service.create_department(
            _context(uuid4(), "employee"), DepartmentInput("FIN", "Finance", "restricted")
        )
    assert repository.organizations == []


@pytest.mark.anyio
async def test_owner_department_write_keeps_server_tenant() -> None:
    """The repository receives tenant scope only from ExecutionContext."""
    repository = FakeRepository()
    service = OrganizationAdministrationService(repository)
    await service.create_department(
        _context(uuid4(), "owner"), DepartmentInput("FIN", "Finance", "restricted")
    )
    assert repository.organizations == ["org-a"]


@pytest.mark.anyio
async def test_privileged_assignment_requires_step_up_and_no_self_assignment() -> None:
    """Owner cannot self-approve and standard sessions cannot grant privilege."""
    actor, target = uuid4(), uuid4()
    service = OrganizationAdministrationService(FakeRepository())
    with pytest.raises(AdministrationDeniedError):
        await service.assign_privileged_role(
            _context(actor, "owner"), target, OrganizationRole.ORGANIZATION_ADMIN
        )
    with pytest.raises(AdministrationDeniedError):
        await service.assign_privileged_role(
            _context(actor, "owner", assurance="step_up"),
            actor,
            OrganizationRole.ORGANIZATION_ADMIN,
        )


@pytest.mark.anyio
async def test_employee_cannot_assign_membership() -> None:
    """Membership administration is denied before persistence for employees."""
    repository = FakeRepository()
    service = OrganizationAdministrationService(repository)
    with pytest.raises(AdministrationDeniedError):
        await service.assign_membership(
            _context(uuid4(), "employee"),
            "department",
            MembershipInput(uuid4(), uuid4()),
        )
    assert repository.memberships == []


@pytest.mark.anyio
async def test_owner_assigns_membership_in_server_tenant() -> None:
    """Client input cannot substitute another organization identifier."""
    repository = FakeRepository()
    actor = uuid4()
    await OrganizationAdministrationService(repository).assign_membership(
        _context(actor, "owner"),
        "department",
        MembershipInput(uuid4(), uuid4()),
    )
    assert repository.memberships[0][0] == "org-a"


@pytest.mark.anyio
async def test_member_status_requires_step_up_owner_and_cannot_self_suspend() -> None:
    """Only a step-up Owner may suspend another member."""
    repository = FakeRepository()
    service = OrganizationAdministrationService(repository)
    actor, target = uuid4(), uuid4()
    with pytest.raises(AdministrationDeniedError):
        await service.set_member_status(_context(actor, "organization_admin"), target, "suspended")
    with pytest.raises(AdministrationDeniedError):
        await service.set_member_status(_context(actor, "owner"), target, "suspended")
    with pytest.raises(AdministrationDeniedError):
        await service.set_member_status(
            _context(actor, "owner", assurance="step_up"), actor, "suspended"
        )
    assert repository.status_changes == []
    await service.set_member_status(
        _context(actor, "owner", assurance="step_up"), target, "suspended"
    )
    assert repository.status_changes == [("org-a", target, "suspended", actor)]


@pytest.mark.anyio
async def test_role_history_is_admin_only_and_tenant_scoped() -> None:
    """The service supplies the tenant from verified context, not from a caller field."""
    repository = FakeRepository()
    service = OrganizationAdministrationService(repository)
    target = uuid4()
    with pytest.raises(AdministrationDeniedError):
        await service.list_role_history(_context(uuid4(), "employee"), target)
    result = await service.list_role_history(_context(uuid4(), "organization_admin"), target)
    assert result == [{"org": "org-a", "user": target}]
