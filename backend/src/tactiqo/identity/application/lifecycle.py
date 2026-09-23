"""Four-eyes tenant lifecycle and ownership use cases."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from tactiqo.identity.application.administration import AdministrationDeniedError
from tactiqo.identity.domain.models import OrganizationRole, SessionAssurance
from tactiqo.shared.domain.execution import ExecutionContext

MIN_RETENTION_DAYS = 7
MAX_RETENTION_DAYS = 365


class TenantLifecycleAction(StrEnum):
    """High-risk tenant changes that require a durable second decision."""

    OWNER_TRANSFER = "owner_transfer"
    SUSPEND = "suspend"
    EXPORT = "export"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class LifecycleRequest:
    """Secret-free lifecycle request view."""

    id: UUID
    action: str
    status: str


@dataclass(frozen=True, slots=True)
class TenantProvisionInput:
    """Provider-neutral initial tenant and immutable Owner identity."""

    organization_id: str
    slug: str
    name: str
    owner_provider: str
    owner_subject: str
    owner_display_name: str
    owner_email: str | None = None


class TenantLifecycleRepository(Protocol):
    """Persist tenant lifecycle requests and atomic decisions."""

    async def create_request(
        self,
        organization_id: str,
        action: TenantLifecycleAction,
        requested_by: UUID,
        target_user_id: UUID | None,
        retention_days: int | None,
    ) -> LifecycleRequest:
        """Create one pending durable request."""

    async def provision(self, command: TenantProvisionInput, provisioned_by: UUID) -> None:
        """Atomically create tenant, immutable Owner identity, membership, and role."""

    async def approve_request(
        self,
        organization_id: str,
        request_id: UUID,
        approved_by: UUID,
    ) -> LifecycleRequest | None:
        """Apply a pending request atomically after four-eyes validation."""


class TenantLifecycleService:
    """Protect owner transfer and destructive tenant state transitions."""

    def __init__(self, repository: TenantLifecycleRepository) -> None:
        """Configure lifecycle persistence."""
        self._repository = repository

    @staticmethod
    def _require_step_up(context: ExecutionContext) -> None:
        if context.session_assurance not in {
            SessionAssurance.MFA.value,
            SessionAssurance.STEP_UP.value,
        }:
            raise AdministrationDeniedError

    async def provision(
        self,
        context: ExecutionContext,
        command: TenantProvisionInput,
    ) -> None:
        """Allow only a step-up platform administrator to provision a tenant."""
        if "platform_admin" not in context.role_codes:
            raise AdministrationDeniedError
        self._require_step_up(context)
        await self._repository.provision(command, UUID(context.actor_id))

    async def request(
        self,
        context: ExecutionContext,
        action: TenantLifecycleAction,
        target_user_id: UUID | None = None,
        retention_days: int | None = None,
    ) -> LifecycleRequest:
        """Allow only a step-up Owner to initiate a high-risk transition."""
        if OrganizationRole.OWNER.value not in context.role_codes:
            raise AdministrationDeniedError
        self._require_step_up(context)
        actor = UUID(context.actor_id)
        if action is TenantLifecycleAction.OWNER_TRANSFER:
            if target_user_id is None or target_user_id == actor:
                raise AdministrationDeniedError
        elif target_user_id is not None:
            raise AdministrationDeniedError
        if action is TenantLifecycleAction.DELETE:
            if retention_days is None or not (
                MIN_RETENTION_DAYS <= retention_days <= MAX_RETENTION_DAYS
            ):
                raise AdministrationDeniedError
        elif retention_days is not None:
            raise AdministrationDeniedError
        return await self._repository.create_request(
            context.organization_id,
            action,
            actor,
            target_user_id,
            retention_days,
        )

    async def approve(
        self,
        context: ExecutionContext,
        request_id: UUID,
    ) -> LifecycleRequest | None:
        """Require a different step-up Owner/Admin to approve the transition."""
        if not {
            OrganizationRole.OWNER.value,
            OrganizationRole.ORGANIZATION_ADMIN.value,
        }.intersection(context.role_codes):
            raise AdministrationDeniedError
        self._require_step_up(context)
        return await self._repository.approve_request(
            context.organization_id,
            request_id,
            UUID(context.actor_id),
        )
