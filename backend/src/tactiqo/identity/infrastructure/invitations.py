"""SQL persistence for tenant-bound invitations."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.identity.application.invitations import InvitationAdminView, InvitationView
from tactiqo.identity.infrastructure.tables import (
    AuthAuditRow,
    DepartmentRow,
    InvitationRow,
    OrganizationRow,
)


class SqlInvitationRepository:
    """Store token digests and require department plus organization predicates."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure transaction factory."""
        self._sessions = sessions

    async def create(
        self, organization_id: str, department_id: UUID, token_hash: str,
        invited_by: UUID, expires_at: datetime,
    ) -> UUID:
        """Insert the invite after verifying its department belongs to this tenant."""
        async with self._sessions() as session, session.begin():
            department = await session.scalar(
                select(DepartmentRow).where(
                    DepartmentRow.id == department_id,
                    DepartmentRow.organization_id == organization_id,
                    DepartmentRow.status == "active",
                )
            )
            if department is None:
                raise ValueError
            row = InvitationRow(
                organization_id=organization_id,
                department_id=department_id,
                email=None,
                token_hash=token_hash,
                invited_by=invited_by,
                expires_at=expires_at,
            )
            session.add(row)
            await session.flush()
            session.add(
                AuthAuditRow(
                    event_type="organization.invitation.created",
                    user_id=invited_by,
                    organization_id=organization_id,
                    correlation_id=str(row.id),
                    safe_detail=f"department={department_id};expires={expires_at.isoformat()}",
                )
            )
            return row.id

    async def inspect(self, token_hash: str) -> InvitationView | None:
        """Expose only active organization and department metadata for a valid link."""
        now = datetime.now(UTC)
        async with self._sessions() as session:
            row = await session.execute(
                select(InvitationRow, OrganizationRow, DepartmentRow)
                .join(OrganizationRow, OrganizationRow.id == InvitationRow.organization_id)
                .join(
                    DepartmentRow,
                    (DepartmentRow.id == InvitationRow.department_id)
                    & (DepartmentRow.organization_id == InvitationRow.organization_id),
                )
                .where(
                    InvitationRow.token_hash == token_hash,
                    InvitationRow.status == "pending",
                    InvitationRow.expires_at > now,
                    OrganizationRow.status == "active",
                    DepartmentRow.status == "active",
                )
            )
            found = row.one_or_none()
            if found is None:
                return None
            invitation, organization, department = found
            return InvitationView(
                organization.id,
                organization.name,
                invitation.department_id,
                department.name,
                invitation.expires_at,
            )

    async def list_for_organization(self, organization_id: str) -> list[InvitationAdminView]:
        """Return at most 200 tenant-owned invitations without bearer data."""
        async with self._sessions() as session:
            rows = await session.execute(
                select(InvitationRow, DepartmentRow)
                .join(
                    DepartmentRow,
                    (DepartmentRow.id == InvitationRow.department_id)
                    & (DepartmentRow.organization_id == InvitationRow.organization_id),
                )
                .where(InvitationRow.organization_id == organization_id)
                .order_by(InvitationRow.expires_at.desc())
                .limit(200)
            )
            return [
                InvitationAdminView(
                    invite.id,
                    invite.department_id,
                    department.name,
                    (
                        "expired"
                        if invite.status == "pending" and invite.expires_at <= datetime.now(UTC)
                        else invite.status
                    ),
                    invite.expires_at,
                )
                for invite, department in rows.all()
            ]

    async def revoke(self, organization_id: str, invitation_id: UUID) -> bool:
        """Revoke pending invitation with exact tenant and identifier predicates."""
        async with self._sessions() as session, session.begin():
            row = await session.scalar(
                select(InvitationRow).where(
                    InvitationRow.id == invitation_id,
                    InvitationRow.organization_id == organization_id,
                    InvitationRow.status == "pending",
                )
            )
            if row is None:
                return False
            row.status = "revoked"
            session.add(
                AuthAuditRow(
                    event_type="organization.invitation.revoked",
                    organization_id=organization_id,
                    correlation_id=str(invitation_id),
                    safe_detail="before=pending;after=revoked",
                )
            )
            return True
