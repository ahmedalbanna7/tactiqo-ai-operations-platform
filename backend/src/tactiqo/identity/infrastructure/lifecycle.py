"""Atomic PostgreSQL tenant lifecycle persistence."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.identity.application.lifecycle import (
    LifecycleRequest,
    TenantLifecycleAction,
    TenantProvisionInput,
)
from tactiqo.identity.infrastructure.tables import (
    AuthAuditRow,
    AuthSessionRow,
    OrganizationMemberRow,
    OrganizationRow,
    RoleAssignmentRow,
    TenantLifecycleRequestRow,
    UserRow,
)


class SqlTenantLifecycleRepository:
    """Persist requests and guarded transitions inside one transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure transaction factory."""
        self._sessions = sessions

    async def provision(self, command: TenantProvisionInput, provisioned_by: UUID) -> None:
        """Create a complete usable tenant boundary in one transaction."""
        async with self._sessions() as session, session.begin():
            existing = await session.scalar(
                select(UserRow).where(
                    UserRow.provider == command.owner_provider,
                    UserRow.subject == command.owner_subject,
                )
            )
            if existing is None:
                existing = UserRow(
                    provider=command.owner_provider,
                    subject=command.owner_subject,
                    display_name=command.owner_display_name,
                    email=command.owner_email,
                )
                session.add(existing)
                await session.flush()
            if await session.get(OrganizationRow, command.organization_id) is not None:
                raise ValueError
            session.add(
                OrganizationRow(
                    id=command.organization_id,
                    slug=command.slug,
                    name=command.name,
                    owner_user_id=existing.id,
                )
            )
            session.add(
                OrganizationMemberRow(
                    organization_id=command.organization_id,
                    user_id=existing.id,
                    status="active",
                )
            )
            session.add(
                RoleAssignmentRow(
                    organization_id=command.organization_id,
                    user_id=existing.id,
                    role_code="owner",
                    assigned_by=provisioned_by,
                )
            )
            session.add(
                AuthAuditRow(
                    event_type="tenant.provisioned",
                    user_id=existing.id,
                    organization_id=command.organization_id,
                    correlation_id=command.organization_id,
                    safe_detail="before=absent;after=active",
                )
            )

    async def create_request(
        self,
        organization_id: str,
        action: TenantLifecycleAction,
        requested_by: UUID,
        target_user_id: UUID | None,
        retention_days: int | None,
    ) -> LifecycleRequest:
        """Validate target membership and store a minimal JSON payload."""
        async with self._sessions() as session, session.begin():
            organization = await session.get(OrganizationRow, organization_id)
            if organization is None or organization.status != "active":
                raise ValueError
            if target_user_id is not None:
                target = await session.get(OrganizationMemberRow, (organization_id, target_user_id))
                if target is None or target.status != "active" or target.revoked_at is not None:
                    raise ValueError
            payload: dict[str, str | int] = {}
            if target_user_id is not None:
                payload["target_user_id"] = str(target_user_id)
            if retention_days is not None:
                payload["retention_days"] = retention_days
                payload["retention_until"] = (
                    datetime.now(UTC) + timedelta(days=retention_days)
                ).isoformat()
            row = TenantLifecycleRequestRow(
                organization_id=organization_id,
                action=action.value,
                requested_by=requested_by,
                payload=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            )
            session.add(row)
            await session.flush()
            session.add(
                AuthAuditRow(
                    event_type="tenant.lifecycle.requested",
                    user_id=requested_by,
                    organization_id=organization_id,
                    correlation_id=str(row.id),
                    safe_detail=f"action={action.value};before=absent;after=pending",
                )
            )
            return LifecycleRequest(row.id, row.action, row.status)

    async def approve_request(
        self,
        organization_id: str,
        request_id: UUID,
        approved_by: UUID,
    ) -> LifecycleRequest | None:
        """Apply one pending transition with tenant, status, and four-eyes predicates."""
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            row = await session.scalar(
                select(TenantLifecycleRequestRow)
                .where(
                    TenantLifecycleRequestRow.id == request_id,
                    TenantLifecycleRequestRow.organization_id == organization_id,
                    TenantLifecycleRequestRow.status == "pending",
                )
                .with_for_update()
            )
            if row is None:
                return None
            if row.requested_by == approved_by:
                raise ValueError
            organization = await session.get(OrganizationRow, organization_id)
            if organization is None:
                return None
            payload = json.loads(row.payload)
            before = organization.status
            if row.action == TenantLifecycleAction.OWNER_TRANSFER.value:
                target_id = UUID(payload["target_user_id"])
                await self._transfer_owner(session, organization, target_id, approved_by, now)
                after = f"owner:{target_id}"
            elif row.action == TenantLifecycleAction.SUSPEND.value:
                organization.status = "suspended"
                await session.execute(
                    update(AuthSessionRow)
                    .where(
                        AuthSessionRow.organization_id == organization_id,
                        AuthSessionRow.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
                after = "suspended"
            elif row.action == TenantLifecycleAction.EXPORT.value:
                after = "export_approved"
            elif row.action == TenantLifecycleAction.DELETE.value:
                organization.status = "deletion_pending"
                after = f"deletion_pending:{payload['retention_until']}"
            else:
                raise ValueError
            row.status = "approved"
            row.approved_by = approved_by
            row.decided_at = now
            session.add(
                AuthAuditRow(
                    event_type="tenant.lifecycle.approved",
                    user_id=approved_by,
                    organization_id=organization_id,
                    correlation_id=str(row.id),
                    safe_detail=f"action={row.action};before={before};after={after}",
                )
            )
            return LifecycleRequest(row.id, row.action, row.status)

    @staticmethod
    async def _transfer_owner(
        session: AsyncSession,
        organization: OrganizationRow,
        target_id: UUID,
        approved_by: UUID,
        now: datetime,
    ) -> None:
        old_owner = organization.owner_user_id
        target = await session.get(OrganizationMemberRow, (organization.id, target_id))
        if target is None or target.status != "active" or target.revoked_at is not None:
            raise ValueError
        organization.owner_user_id = target_id
        await session.execute(
            update(RoleAssignmentRow)
            .where(
                RoleAssignmentRow.organization_id == organization.id,
                RoleAssignmentRow.user_id == old_owner,
                RoleAssignmentRow.role_code == "owner",
                RoleAssignmentRow.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoked_by=approved_by)
        )
        existing = await session.scalar(
            select(RoleAssignmentRow.id).where(
                RoleAssignmentRow.organization_id == organization.id,
                RoleAssignmentRow.user_id == target_id,
                RoleAssignmentRow.role_code == "owner",
                RoleAssignmentRow.revoked_at.is_(None),
            )
        )
        if existing is None:
            session.add(
                RoleAssignmentRow(
                    organization_id=organization.id,
                    user_id=target_id,
                    role_code="owner",
                    assigned_by=approved_by,
                )
            )
