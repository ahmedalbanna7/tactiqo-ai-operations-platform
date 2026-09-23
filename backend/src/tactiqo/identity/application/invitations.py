"""Owner-managed, single-use organization invitation links."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from tactiqo.identity.application.administration import AdministrationDeniedError
from tactiqo.identity.domain.models import OrganizationRole
from tactiqo.shared.domain.execution import ExecutionContext

MIN_TOKEN_LENGTH = 40
MAX_TOKEN_LENGTH = 128


@dataclass(frozen=True, slots=True)
class InvitationView:
    """Safe invitation details that never include the bearer token."""

    organization_id: str
    organization_name: str
    department_id: UUID
    department_name: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class InvitationAdminView:
    """Non-secret invitation history for its owning organization."""

    id: UUID
    department_id: UUID
    department_name: str
    status: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CreatedInvitation:
    """One-time returned bearer link material and expiry."""

    invitation_id: UUID
    organization_id: str
    department_id: UUID
    token: str
    expires_at: datetime


class InvitationRepository(Protocol):
    """Tenant-safe invitation persistence."""

    async def create(
        self, organization_id: str, department_id: UUID, token_hash: str,
        invited_by: UUID, expires_at: datetime,
    ) -> UUID:
        """Create a tenant and department-bound token digest."""

    async def inspect(self, token_hash: str) -> InvitationView | None:
        """Resolve unexpired pending invite metadata from its digest."""

    async def list_for_organization(self, organization_id: str) -> list[InvitationAdminView]:
        """Return bounded secret-free invitation history for one tenant."""

    async def revoke(self, organization_id: str, invitation_id: UUID) -> bool:
        """Revoke one pending invitation in the exact tenant."""


class OrganizationInvitationService:
    """Authorize invitation management and issue high-entropy single-use tokens."""

    def __init__(self, repository: InvitationRepository) -> None:
        """Configure tenant-scoped persistence."""
        self._repository = repository

    @staticmethod
    def _require_admin(context: ExecutionContext) -> None:
        administrators = {
            OrganizationRole.OWNER.value,
            OrganizationRole.ORGANIZATION_ADMIN.value,
        }
        if not administrators.intersection(context.role_codes):
            raise AdministrationDeniedError

    async def create(
        self, context: ExecutionContext, department_id: UUID
    ) -> CreatedInvitation:
        """Create one 72-hour invitation, exposing its random token only once."""
        self._require_admin(context)
        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(UTC) + timedelta(hours=72)
        invitation_id = await self._repository.create(
            context.organization_id,
            department_id,
            hashlib.sha256(token.encode()).hexdigest(),
            UUID(context.actor_id),
            expires_at,
        )
        return CreatedInvitation(
            invitation_id, context.organization_id, department_id, token, expires_at
        )

    async def inspect(self, token: str) -> InvitationView | None:
        """Resolve a bearer token without exposing stored token material."""
        if len(token) < MIN_TOKEN_LENGTH or len(token) > MAX_TOKEN_LENGTH:
            return None
        return await self._repository.inspect(hashlib.sha256(token.encode()).hexdigest())

    async def list(self, context: ExecutionContext) -> list[InvitationAdminView]:
        """List invitation status for an authorized organization administrator."""
        self._require_admin(context)
        return await self._repository.list_for_organization(context.organization_id)

    async def revoke(
        self, context: ExecutionContext, invitation_id: UUID
    ) -> bool:
        """Revoke a pending invitation after rechecking tenant administrator authority."""
        self._require_admin(context)
        return await self._repository.revoke(context.organization_id, invitation_id)
