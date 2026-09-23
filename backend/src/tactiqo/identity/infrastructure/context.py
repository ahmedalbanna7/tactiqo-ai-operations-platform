"""PostgreSQL execution-context reconstruction with current revocation checks."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.identity.infrastructure.tables import (
    AuthSessionRow,
    DepartmentMemberRow,
    OrganizationMemberRow,
    OrganizationRow,
    ProjectMemberRow,
    RoleAssignmentRow,
    TeamMemberRow,
    UserRow,
)
from tactiqo.shared.domain.execution import ExecutionContext


class SqlExecutionContextResolver:
    """Rebuild minimum effective scope for every request and resumed operation."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure the transaction factory."""
        self._sessions = sessions

    async def resolve(self, opaque_session: str, correlation_id: str) -> ExecutionContext | None:
        """Resolve an active session and current dated memberships, fail closed."""
        token_hash = hashlib.sha256(opaque_session.encode()).hexdigest()
        now = datetime.now(UTC)
        async with self._sessions() as session:
            result = await session.execute(
                select(AuthSessionRow, UserRow, OrganizationRow, OrganizationMemberRow)
                .join(UserRow, UserRow.id == AuthSessionRow.user_id)
                .join(OrganizationRow, OrganizationRow.id == AuthSessionRow.organization_id)
                .join(
                    OrganizationMemberRow,
                    and_(
                        OrganizationMemberRow.organization_id == AuthSessionRow.organization_id,
                        OrganizationMemberRow.user_id == AuthSessionRow.user_id,
                    ),
                )
                .where(
                    AuthSessionRow.token_hash == token_hash,
                    AuthSessionRow.revoked_at.is_(None),
                    AuthSessionRow.expires_at > now,
                    UserRow.active.is_(True),
                    OrganizationRow.status == "active",
                    OrganizationMemberRow.status == "active",
                    OrganizationMemberRow.revoked_at.is_(None),
                    OrganizationMemberRow.valid_from <= now,
                    (
                        OrganizationMemberRow.valid_until.is_(None)
                        | (OrganizationMemberRow.valid_until > now)
                    ),
                )
            )
            row = result.one_or_none()
            if row is None:
                return None
            auth_session, user, organization, membership = row
            roles = tuple(
                (
                    await session.scalars(
                    select(RoleAssignmentRow.role_code).where(
                        RoleAssignmentRow.organization_id == organization.id,
                        RoleAssignmentRow.user_id == user.id,
                        RoleAssignmentRow.revoked_at.is_(None),
                        RoleAssignmentRow.valid_from <= now,
                        (
                            RoleAssignmentRow.valid_until.is_(None)
                            | (RoleAssignmentRow.valid_until > now)
                        ),
                        )
                    )
                ).all()
            )
            departments = tuple(
                str(value)
                for value in (
                    await session.scalars(
                        select(DepartmentMemberRow.department_id).where(
                            DepartmentMemberRow.organization_id == organization.id,
                            DepartmentMemberRow.user_id == user.id,
                            DepartmentMemberRow.revoked_at.is_(None),
                            DepartmentMemberRow.valid_from <= now,
                            (
                                DepartmentMemberRow.valid_until.is_(None)
                                | (DepartmentMemberRow.valid_until > now)
                            ),
                        )
                    )
                ).all()
            )
            teams = tuple(
                str(value)
                for value in (
                    await session.scalars(
                        select(TeamMemberRow.team_id).where(
                            TeamMemberRow.organization_id == organization.id,
                            TeamMemberRow.user_id == user.id,
                            TeamMemberRow.revoked_at.is_(None),
                            TeamMemberRow.valid_from <= now,
                        )
                    )
                ).all()
            )
            projects = tuple(
                str(value)
                for value in (
                    await session.scalars(
                        select(ProjectMemberRow.project_id).where(
                            ProjectMemberRow.organization_id == organization.id,
                            ProjectMemberRow.user_id == user.id,
                            ProjectMemberRow.revoked_at.is_(None),
                            ProjectMemberRow.valid_from <= now,
                        )
                    )
                ).all()
            )
            if "employee" in roles and not departments:
                return None
            return ExecutionContext(
                actor_id=str(user.id),
                organization_id=organization.id,
                correlation_id=correlation_id,
                classification_clearance=membership.classification_clearance,
                policy_version=organization.policy_version,
                organizational_unit_ids=departments,
                department_ids=departments,
                team_ids=teams,
                project_ids=projects,
                role_codes=roles,
                data_region=organization.data_region,
                session_id=str(auth_session.id),
                session_assurance=auth_session.assurance,
            )

    async def resolve_delegated(
        self,
        actor_id: str,
        organization_id: str,
        correlation_id: str,
        session_assurance: str,
    ) -> ExecutionContext | None:
        """Rebuild current authority for signed background work without a browser token."""
        try:
            user_id = UUID(actor_id)
        except ValueError:
            return None
        now = datetime.now(UTC)
        async with self._sessions() as session:
            result = await session.execute(
                select(UserRow, OrganizationRow, OrganizationMemberRow)
                .select_from(UserRow)
                .join(
                    OrganizationMemberRow,
                    OrganizationMemberRow.user_id == UserRow.id,
                )
                .join(
                    OrganizationRow,
                    OrganizationRow.id == OrganizationMemberRow.organization_id,
                )
                .where(
                    UserRow.id == user_id,
                    OrganizationRow.id == organization_id,
                    UserRow.active.is_(True),
                    OrganizationRow.status == "active",
                    OrganizationMemberRow.status == "active",
                    OrganizationMemberRow.revoked_at.is_(None),
                    OrganizationMemberRow.valid_from <= now,
                    (
                        OrganizationMemberRow.valid_until.is_(None)
                        | (OrganizationMemberRow.valid_until > now)
                    ),
                )
            )
            row = result.one_or_none()
            if row is None:
                return None
            user, organization, membership = row
            roles = tuple(
                (
                    await session.scalars(
                        select(RoleAssignmentRow.role_code).where(
                            RoleAssignmentRow.organization_id == organization.id,
                            RoleAssignmentRow.user_id == user.id,
                            RoleAssignmentRow.revoked_at.is_(None),
                            RoleAssignmentRow.valid_from <= now,
                            (
                                RoleAssignmentRow.valid_until.is_(None)
                                | (RoleAssignmentRow.valid_until > now)
                            ),
                        )
                    )
                ).all()
            )
            departments = tuple(
                str(value)
                for value in (
                    await session.scalars(
                        select(DepartmentMemberRow.department_id).where(
                            DepartmentMemberRow.organization_id == organization.id,
                            DepartmentMemberRow.user_id == user.id,
                            DepartmentMemberRow.revoked_at.is_(None),
                        )
                    )
                ).all()
            )
            teams = tuple(
                str(value)
                for value in (
                    await session.scalars(
                        select(TeamMemberRow.team_id).where(
                            TeamMemberRow.organization_id == organization.id,
                            TeamMemberRow.user_id == user.id,
                            TeamMemberRow.revoked_at.is_(None),
                        )
                    )
                ).all()
            )
            projects = tuple(
                str(value)
                for value in (
                    await session.scalars(
                        select(ProjectMemberRow.project_id).where(
                            ProjectMemberRow.organization_id == organization.id,
                            ProjectMemberRow.user_id == user.id,
                            ProjectMemberRow.revoked_at.is_(None),
                        )
                    )
                ).all()
            )
            if "employee" in roles and not departments:
                return None
            return ExecutionContext(
                actor_id=str(user.id),
                organization_id=organization.id,
                correlation_id=correlation_id,
                classification_clearance=membership.classification_clearance,
                policy_version=organization.policy_version,
                organizational_unit_ids=departments,
                department_ids=departments,
                team_ids=teams,
                project_ids=projects,
                role_codes=roles,
                data_region=organization.data_region,
                session_assurance=session_assurance,
            )
