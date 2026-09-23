"""Tenant-predicated organization administration persistence."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.identity.application.administration import (
    LAST_OWNER_ERROR,
    ChildUnitInput,
    DepartmentInput,
    MemberDetail,
    MembershipInput,
    UnitDetail,
    UnitRecord,
)
from tactiqo.identity.infrastructure.tables import (
    AuthAuditRow,
    AuthSessionRow,
    DepartmentMemberRow,
    DepartmentRow,
    OrganizationMemberRow,
    OrganizationRow,
    ProjectMemberRow,
    ProjectRow,
    RoleAssignmentRow,
    TeamMemberRow,
    TeamRow,
    UserRow,
)


class SqlOrganizationAdministrationRepository:
    """Persist authorized changes with exact organization predicates."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure the transaction factory."""
        self._sessions = sessions

    async def list_people(self, organization_id: str) -> list[MemberDetail]:
        """Bound a tenant people listing before resolving active role codes."""
        now = datetime.now(UTC)
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(OrganizationMemberRow, UserRow)
                    .join(UserRow, UserRow.id == OrganizationMemberRow.user_id)
                    .where(OrganizationMemberRow.organization_id == organization_id)
                    .order_by(UserRow.display_name)
                    .limit(200)
                )
            ).all()
            user_ids = [member.user_id for member, _ in rows]
            roles = (
                await session.scalars(
                    select(RoleAssignmentRow).where(
                        RoleAssignmentRow.organization_id == organization_id,
                        RoleAssignmentRow.user_id.in_(user_ids),
                        RoleAssignmentRow.revoked_at.is_(None),
                        RoleAssignmentRow.valid_from <= now,
                        (
                            RoleAssignmentRow.valid_until.is_(None)
                            | (RoleAssignmentRow.valid_until > now)
                        ),
                    )
                )
            ).all() if user_ids else []
        roles_by_user: dict[UUID, list[str]] = {}
        for role in roles:
            roles_by_user.setdefault(role.user_id, []).append(role.role_code)
        return [
            MemberDetail(
                user_id=member.user_id,
                display_name=user.display_name,
                email=user.email,
                status=member.status if user.active else "inactive",
                classification_clearance=member.classification_clearance,
                role_codes=tuple(sorted(roles_by_user.get(member.user_id, []))),
            )
            for member, user in rows
        ]

    async def set_member_status(
        self, organization_id: str, user_id: UUID, status: str, changed_by: UUID
    ) -> bool:
        """Update one membership and revoke its sessions in this tenant atomically."""
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            await session.scalar(
                select(OrganizationRow)
                .where(OrganizationRow.id == organization_id)
                .with_for_update()
            )
            member = await session.get(OrganizationMemberRow, (organization_id, user_id))
            if member is None or member.revoked_at is not None:
                return False
            if member.status == status:
                return True
            if status == "suspended":
                owners = list((await session.scalars(
                    select(RoleAssignmentRow.user_id).join(
                        OrganizationMemberRow,
                        (OrganizationMemberRow.organization_id == RoleAssignmentRow.organization_id)
                        & (OrganizationMemberRow.user_id == RoleAssignmentRow.user_id),
                    ).where(
                        RoleAssignmentRow.organization_id == organization_id,
                        RoleAssignmentRow.role_code == "owner",
                        RoleAssignmentRow.revoked_at.is_(None),
                        RoleAssignmentRow.valid_from <= now,
                        (
                            RoleAssignmentRow.valid_until.is_(None)
                            | (RoleAssignmentRow.valid_until > now)
                        ),
                        OrganizationMemberRow.status == "active",
                        OrganizationMemberRow.revoked_at.is_(None),
                    )
                )).all())
                if user_id in owners and len(set(owners)) <= 1:
                    raise ValueError(LAST_OWNER_ERROR)
            previous = member.status
            member.status = status
            if status == "suspended":
                await session.execute(
                    update(AuthSessionRow)
                    .where(
                        AuthSessionRow.user_id == user_id,
                        AuthSessionRow.organization_id == organization_id,
                        AuthSessionRow.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
            session.add(AuthAuditRow(
                event_type=f"organization.member.{status}", user_id=user_id,
                organization_id=organization_id, correlation_id=str(user_id),
                safe_detail=f"before={previous};after={status};changed_by={changed_by}",
            ))
            return True

    async def list_role_history(
        self, organization_id: str, user_id: UUID
    ) -> list[dict[str, object]]:
        """Return current and revoked tenant role grants, bounded and secret-free."""
        async with self._sessions() as session:
            member = await session.get(OrganizationMemberRow, (organization_id, user_id))
            if member is None:
                return []
            rows = (await session.scalars(
                select(RoleAssignmentRow).where(
                    RoleAssignmentRow.organization_id == organization_id,
                    RoleAssignmentRow.user_id == user_id,
                ).order_by(RoleAssignmentRow.valid_from.desc()).limit(100)
            )).all()
        return [{"id": row.id, "role_code": row.role_code, "scope_type": row.scope_type,
                 "scope_id": row.scope_id, "valid_from": row.valid_from,
                 "valid_until": row.valid_until, "revoked_at": row.revoked_at,
                 "revoked_by": row.revoked_by, "assigned_by": row.assigned_by}
                for row in rows]

    async def revoke_role(
        self, organization_id: str, assignment_id: UUID, revoked_by: UUID
    ) -> bool:
        """Revoke a tenant-scoped assignment, protecting the final active owner."""
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            await session.scalar(
                select(OrganizationRow)
                .where(OrganizationRow.id == organization_id)
                .with_for_update()
            )
            assignment = await session.scalar(select(RoleAssignmentRow).where(
                RoleAssignmentRow.id == assignment_id,
                RoleAssignmentRow.organization_id == organization_id,
                RoleAssignmentRow.revoked_at.is_(None),
            ))
            if assignment is None:
                return False
            if assignment.role_code == "owner":
                owners = list((await session.scalars(select(RoleAssignmentRow.user_id).join(
                    OrganizationMemberRow,
                    (OrganizationMemberRow.organization_id == RoleAssignmentRow.organization_id)
                    & (OrganizationMemberRow.user_id == RoleAssignmentRow.user_id),
                ).where(
                    RoleAssignmentRow.organization_id == organization_id,
                    RoleAssignmentRow.role_code == "owner",
                    RoleAssignmentRow.revoked_at.is_(None),
                    RoleAssignmentRow.valid_from <= now,
                    (
                        RoleAssignmentRow.valid_until.is_(None)
                        | (RoleAssignmentRow.valid_until > now)
                    ),
                    OrganizationMemberRow.status == "active",
                    OrganizationMemberRow.revoked_at.is_(None),
                ))).all())
                if assignment.user_id in owners and len(set(owners)) <= 1:
                    raise ValueError(LAST_OWNER_ERROR)
            assignment.revoked_at = now
            assignment.revoked_by = revoked_by
            session.add(AuthAuditRow(
                event_type="role.revoked", user_id=assignment.user_id,
                organization_id=organization_id, correlation_id=str(assignment_id),
                safe_detail=f"before={assignment.role_code};after=revoked;revoked_by={revoked_by}",
            ))
            return True

    async def list_units(self, organization_id: str) -> list[UnitDetail]:
        """Return only active exact-tenant units in a bounded ordered listing."""
        async with self._sessions() as session:
            departments = (
                await session.scalars(
                    select(DepartmentRow).where(
                        DepartmentRow.organization_id == organization_id,
                        DepartmentRow.status == "active",
                    ).order_by(DepartmentRow.name).limit(200)
                )
            ).all()
            teams = (
                await session.scalars(
                    select(TeamRow).where(
                        TeamRow.organization_id == organization_id,
                        TeamRow.status == "active",
                    ).order_by(TeamRow.name).limit(500)
                )
            ).all()
            projects = (
                await session.scalars(
                    select(ProjectRow).where(
                        ProjectRow.organization_id == organization_id,
                        ProjectRow.status == "active",
                    ).order_by(ProjectRow.name).limit(500)
                )
            ).all()
        return [
            UnitDetail(row.id, "department", row.code, row.name, None,
                       row.manager_user_id, row.classification_ceiling, row.status)
            for row in departments
        ] + [
            UnitDetail(row.id, "team", str(row.id), row.name, row.department_id,
                       row.manager_user_id, None, row.status)
            for row in teams
        ] + [
            UnitDetail(row.id, "project", row.code, row.name, row.department_id,
                       row.manager_user_id, None, row.status)
            for row in projects
        ]

    async def create_department(self, organization_id: str, command: DepartmentInput) -> UnitRecord:
        """Create a department after validating its manager belongs to the tenant."""
        async with self._sessions() as session, session.begin():
            if command.manager_user_id is not None:
                member = await session.get(
                    OrganizationMemberRow, (organization_id, command.manager_user_id)
                )
                user = await session.get(UserRow, command.manager_user_id)
                if (
                    member is None or member.status != "active"
                    or member.revoked_at is not None or user is None or not user.active
                ):
                    raise ValueError
            row = DepartmentRow(
                organization_id=organization_id,
                code=command.code,
                name=command.name,
                manager_user_id=command.manager_user_id,
                classification_ceiling=command.classification_ceiling,
            )
            session.add(row)
            await session.flush()
            return UnitRecord(row.id, row.code, row.name)

    async def assign_role(
        self,
        organization_id: str,
        user_id: UUID,
        role_code: str,
        assigned_by: UUID,
    ) -> None:
        """Assign privilege only to an active member and write safe before/after audit."""
        async with self._sessions() as session, session.begin():
            member = await session.get(OrganizationMemberRow, (organization_id, user_id))
            if member is None or member.status != "active" or member.revoked_at is not None:
                raise ValueError
            existing = await session.scalar(
                select(RoleAssignmentRow.id).where(
                    RoleAssignmentRow.organization_id == organization_id,
                    RoleAssignmentRow.user_id == user_id,
                    RoleAssignmentRow.role_code == role_code,
                    RoleAssignmentRow.revoked_at.is_(None),
                )
            )
            if existing is not None:
                return
            assignment = RoleAssignmentRow(
                organization_id=organization_id,
                user_id=user_id,
                role_code=role_code,
                assigned_by=assigned_by,
            )
            session.add(assignment)
            await session.flush()
            session.add(
                AuthAuditRow(
                    event_type="role.assigned",
                    user_id=user_id,
                    organization_id=organization_id,
                    correlation_id=str(assignment.id),
                    safe_detail=f"before=absent;after={role_code};assigned_by={assigned_by}",
                )
            )

    async def create_team(self, organization_id: str, command: ChildUnitInput) -> UnitRecord:
        """Create a team only beneath a department in the same tenant."""
        async with self._sessions() as session, session.begin():
            department = await session.scalar(
                select(DepartmentRow).where(
                    DepartmentRow.id == command.department_id,
                    DepartmentRow.organization_id == organization_id,
                )
            )
            if department is None:
                raise ValueError
            if command.manager_user_id is not None:
                manager = await session.get(
                    DepartmentMemberRow,
                    (organization_id, department.id, command.manager_user_id),
                )
                user = await session.get(UserRow, command.manager_user_id)
                if (
                    manager is None or manager.revoked_at is not None
                    or user is None or not user.active
                ):
                    raise ValueError
            row = TeamRow(
                organization_id=organization_id,
                department_id=department.id,
                name=command.name,
                manager_user_id=command.manager_user_id,
            )
            session.add(row)
            await session.flush()
            return UnitRecord(row.id, command.code or str(row.id), row.name)

    async def create_project(self, organization_id: str, command: ChildUnitInput) -> UnitRecord:
        """Create a project only beneath a department in the same tenant."""
        if not command.code:
            raise ValueError
        async with self._sessions() as session, session.begin():
            department = await session.scalar(
                select(DepartmentRow).where(
                    DepartmentRow.id == command.department_id,
                    DepartmentRow.organization_id == organization_id,
                )
            )
            if department is None:
                raise ValueError
            if command.manager_user_id is not None:
                manager = await session.get(
                    OrganizationMemberRow,
                    (organization_id, command.manager_user_id),
                )
                user = await session.get(UserRow, command.manager_user_id)
                if (
                    manager is None or manager.status != "active"
                    or manager.revoked_at is not None or user is None or not user.active
                ):
                    raise ValueError
            row = ProjectRow(
                organization_id=organization_id,
                department_id=department.id,
                code=command.code,
                name=command.name,
                manager_user_id=command.manager_user_id,
            )
            session.add(row)
            await session.flush()
            return UnitRecord(row.id, row.code, row.name)

    async def assign_membership(
        self,
        organization_id: str,
        kind: str,
        command: MembershipInput,
        assigned_by: UUID,
    ) -> None:
        """Assign membership while preserving tenant and hierarchy boundaries."""
        async with self._sessions() as session, session.begin():
            membership_row: DepartmentMemberRow | TeamMemberRow | ProjectMemberRow
            member = await session.get(OrganizationMemberRow, (organization_id, command.user_id))
            user = await session.get(UserRow, command.user_id)
            if (
                member is None or member.status != "active"
                or member.revoked_at is not None or user is None or not user.active
            ):
                raise ValueError
            if kind == "department":
                unit = await session.scalar(
                    select(DepartmentRow).where(
                        DepartmentRow.id == command.unit_id,
                        DepartmentRow.organization_id == organization_id,
                    )
                )
                if unit is None:
                    raise ValueError
                membership_row = DepartmentMemberRow(
                    organization_id=organization_id,
                    department_id=unit.id,
                    user_id=command.user_id,
                )
            elif kind == "team":
                unit = await session.scalar(
                    select(TeamRow).where(
                        TeamRow.id == command.unit_id,
                        TeamRow.organization_id == organization_id,
                    )
                )
                if unit is None:
                    raise ValueError
                department_membership = await session.get(
                    DepartmentMemberRow,
                    (organization_id, unit.department_id, command.user_id),
                )
                if department_membership is None or department_membership.revoked_at is not None:
                    raise ValueError
                membership_row = TeamMemberRow(
                    organization_id=organization_id,
                    team_id=unit.id,
                    user_id=command.user_id,
                )
            elif kind == "project":
                unit = await session.scalar(
                    select(ProjectRow).where(
                        ProjectRow.id == command.unit_id,
                        ProjectRow.organization_id == organization_id,
                    )
                )
                if unit is None:
                    raise ValueError
                membership_row = ProjectMemberRow(
                    organization_id=organization_id,
                    project_id=unit.id,
                    user_id=command.user_id,
                )
            else:
                raise ValueError
            session.add(membership_row)
            session.add(
                AuthAuditRow(
                    event_type=f"{kind}.membership.assigned",
                    user_id=command.user_id,
                    organization_id=organization_id,
                    correlation_id=str(command.unit_id),
                    safe_detail=f"before=absent;after=active;assigned_by={assigned_by}",
                )
            )
