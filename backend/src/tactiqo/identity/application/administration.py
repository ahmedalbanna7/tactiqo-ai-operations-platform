"""Authorization-first organization administration use cases."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from tactiqo.identity.domain.models import OrganizationRole, SessionAssurance
from tactiqo.shared.domain.execution import ExecutionContext


class AdministrationDeniedError(PermissionError):
    """Generic denial that does not disclose hidden resources."""


LAST_OWNER_ERROR = "last_owner"


@dataclass(frozen=True, slots=True)
class DepartmentInput:
    """Validated department creation data."""

    code: str
    name: str
    classification_ceiling: str
    manager_user_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class UnitRecord:
    """Minimal secret-free organizational unit result."""

    id: UUID
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class UnitDetail:
    """Tenant-scoped organizational unit shown in Company Settings."""

    id: UUID
    kind: str
    code: str
    name: str
    department_id: UUID | None
    manager_user_id: UUID | None
    classification_ceiling: str | None
    status: str


@dataclass(frozen=True, slots=True)
class MemberDetail:
    """Administrative, bounded people-directory record."""

    user_id: UUID
    display_name: str
    email: str | None
    status: str
    classification_clearance: str
    role_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChildUnitInput:
    """Create a team or project below an owning department."""

    department_id: UUID
    name: str
    code: str | None = None
    manager_user_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class MembershipInput:
    """Assign one active organization member to a bounded unit."""

    unit_id: UUID
    user_id: UUID


class OrganizationAdministrationRepository(Protocol):
    """Tenant-predicated persistence operations."""

    async def create_department(self, organization_id: str, command: DepartmentInput) -> UnitRecord:
        """Create a department inside the exact organization."""

    async def list_units(self, organization_id: str) -> list[UnitDetail]:
        """List exact-tenant departments, teams and projects."""

    async def list_people(self, organization_id: str) -> list[MemberDetail]:
        """List exact-tenant members and active role codes for admins."""

    async def assign_role(
        self,
        organization_id: str,
        user_id: UUID,
        role_code: str,
        assigned_by: UUID,
    ) -> None:
        """Create one dated role assignment and audit before/after state."""

    async def set_member_status(
        self, organization_id: str, user_id: UUID, status: str, changed_by: UUID
    ) -> bool:
        """Change membership lifecycle, revoke sessions and write audit atomically."""

    async def list_role_history(
        self, organization_id: str, user_id: UUID
    ) -> list[dict[str, object]]:
        """Return bounded assignment history for one exact-tenant member."""

    async def revoke_role(
        self, organization_id: str, assignment_id: UUID, revoked_by: UUID
    ) -> bool:
        """Revoke one exact-tenant role assignment and audit the change."""

    async def create_team(self, organization_id: str, command: ChildUnitInput) -> UnitRecord:
        """Create a team bounded by an organization department."""

    async def create_project(self, organization_id: str, command: ChildUnitInput) -> UnitRecord:
        """Create a project bounded by its owning department."""

    async def assign_membership(
        self,
        organization_id: str,
        kind: str,
        command: MembershipInput,
        assigned_by: UUID,
    ) -> None:
        """Assign an active member with exact hierarchy predicates."""


class OrganizationAdministrationService:
    """Enforce administration and step-up rules before persistence."""

    def __init__(self, repository: OrganizationAdministrationRepository) -> None:
        """Configure a tenant-safe repository."""
        self._repository = repository

    @staticmethod
    def _require_admin(context: ExecutionContext) -> None:
        allowed = {OrganizationRole.OWNER.value, OrganizationRole.ORGANIZATION_ADMIN.value}
        if not allowed.intersection(context.role_codes):
            raise AdministrationDeniedError

    @staticmethod
    def _require_step_up(context: ExecutionContext) -> None:
        if context.session_assurance not in {
            SessionAssurance.MFA.value,
            SessionAssurance.STEP_UP.value,
        }:
            raise AdministrationDeniedError

    async def create_department(
        self, context: ExecutionContext, command: DepartmentInput
    ) -> UnitRecord:
        """Allow an Owner/Admin to create a department in their own tenant."""
        self._require_admin(context)
        return await self._repository.create_department(context.organization_id, command)

    async def list_units(self, context: ExecutionContext) -> list[UnitDetail]:
        """Show structure only to a company administrator."""
        self._require_admin(context)
        return await self._repository.list_units(context.organization_id)

    async def list_people(self, context: ExecutionContext) -> list[MemberDetail]:
        """Show the tenant people directory only to an administrator."""
        self._require_admin(context)
        return await self._repository.list_people(context.organization_id)

    async def set_member_status(
        self, context: ExecutionContext, user_id: UUID, status: str
    ) -> bool:
        """Only an Owner may change membership status, with recent step-up assurance."""
        if OrganizationRole.OWNER.value not in context.role_codes:
            raise AdministrationDeniedError
        self._require_step_up(context)
        if status not in {"active", "suspended"} or UUID(context.actor_id) == user_id:
            raise AdministrationDeniedError
        return await self._repository.set_member_status(
            context.organization_id, user_id, status, UUID(context.actor_id)
        )

    async def list_role_history(
        self, context: ExecutionContext, user_id: UUID
    ) -> list[dict[str, object]]:
        """Owner/Admin can inspect bounded role history, never another tenant."""
        self._require_admin(context)
        return await self._repository.list_role_history(context.organization_id, user_id)

    async def revoke_role(
        self, context: ExecutionContext, assignment_id: UUID
    ) -> bool:
        """Only a step-up Owner may revoke role history entries."""
        if OrganizationRole.OWNER.value not in context.role_codes:
            raise AdministrationDeniedError
        self._require_step_up(context)
        return await self._repository.revoke_role(
            context.organization_id, assignment_id, UUID(context.actor_id)
        )

    async def create_team(self, context: ExecutionContext, command: ChildUnitInput) -> UnitRecord:
        """Allow an Owner/Admin to create one department-bounded team."""
        self._require_admin(context)
        return await self._repository.create_team(context.organization_id, command)

    async def create_project(
        self, context: ExecutionContext, command: ChildUnitInput
    ) -> UnitRecord:
        """Allow an Owner/Admin to create one department-owned project."""
        self._require_admin(context)
        return await self._repository.create_project(context.organization_id, command)

    async def assign_privileged_role(
        self,
        context: ExecutionContext,
        user_id: UUID,
        role: OrganizationRole,
    ) -> None:
        """Allow only a step-up Owner to grant organization-wide privilege."""
        if OrganizationRole.OWNER.value not in context.role_codes:
            raise AdministrationDeniedError
        self._require_step_up(context)
        if role not in {
            OrganizationRole.ORGANIZATION_ADMIN,
            OrganizationRole.INTEGRATION_MANAGER,
        }:
            raise AdministrationDeniedError
        actor = UUID(context.actor_id)
        if actor == user_id:
            raise AdministrationDeniedError
        await self._repository.assign_role(
            context.organization_id,
            user_id,
            role.value,
            actor,
        )

    async def assign_membership(
        self,
        context: ExecutionContext,
        kind: str,
        command: MembershipInput,
    ) -> None:
        """Allow Owner/Admin to assign department, team, or project membership."""
        self._require_admin(context)
        if kind not in {"department", "team", "project"}:
            raise AdministrationDeniedError
        await self._repository.assign_membership(
            context.organization_id,
            kind,
            command,
            UUID(context.actor_id),
        )
