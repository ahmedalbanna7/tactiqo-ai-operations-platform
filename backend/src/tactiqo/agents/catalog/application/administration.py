"""Owner-controlled Agent Catalog lifecycle and assignment use cases."""

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from tactiqo.authorization.domain.models import PolicyAction, PolicyEffect, PolicyObligation
from tactiqo.identity.application.administration import AdministrationDeniedError
from tactiqo.identity.domain.models import OrganizationRole
from tactiqo.shared.domain.execution import ExecutionContext


@dataclass(frozen=True, slots=True)
class AgentAssignmentInput:
    """One bounded assignment and its independently stored action grants."""

    agent_code: str
    target_type: str
    target_id: str
    actions: tuple[PolicyAction, ...]
    effect: PolicyEffect = PolicyEffect.ALLOW
    classification_ceiling: str = "internal"
    data_domains: tuple[str, ...] = field(default_factory=tuple)
    connection_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_names: tuple[str, ...] = field(default_factory=tuple)
    quota: dict[str, int] = field(default_factory=dict)
    budget: dict[str, int] = field(default_factory=dict)
    obligations: tuple[PolicyObligation, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AgentAssignmentDetail:
    """Secret-free tenant assignment for an administrator."""

    id: UUID
    agent_code: str
    target_type: str
    target_id: str
    actions: tuple[str, ...]
    effect: str
    classification_ceiling: str
    active: bool


@dataclass(frozen=True, slots=True)
class AgentCatalogItem:
    """Safe definition/version choices and tenant lifecycle state for settings."""

    code: str
    name: str
    description: str
    category: str
    selected_version: str
    versions: tuple[str, ...]
    installed: bool
    enabled: bool


@dataclass(frozen=True, slots=True)
class AgentApprovalChainInput:
    """One ordered approval chain selected by action, risk, and target system."""

    agent_code: str
    action: PolicyAction
    risk: str
    target_system: str
    approver_steps: tuple[str, ...]


class AgentCatalogAdministrationRepository(Protocol):
    """Tenant-safe catalog mutation port."""

    async def install(
        self, organization_id: str, agent_code: str, version: str, actor_id: UUID
    ) -> None:
        """Install or select one immutable version."""

    async def list_assignments(self, organization_id: str) -> list[AgentAssignmentDetail]:
        """Return bounded exact-tenant assignment metadata."""

    async def list_catalog(self, organization_id: str) -> list[AgentCatalogItem]:
        """Return a bounded catalog with safe version and install status."""

    async def set_enabled(self, organization_id: str, agent_code: str, *, enabled: bool) -> bool:
        """Enable or disable an installed agent and bump policy version."""

    async def assign(
        self,
        organization_id: str,
        command: AgentAssignmentInput,
        actor_id: UUID,
    ) -> UUID:
        """Create grants, scopes, quotas, tools, and obligations atomically."""

    async def revoke_assignment(self, organization_id: str, assignment_id: UUID) -> bool:
        """Immediately revoke one tenant assignment and bump policy version."""

    async def set_approval_chain(
        self,
        organization_id: str,
        command: AgentApprovalChainInput,
        actor_id: UUID,
    ) -> UUID:
        """Create or replace one tenant approval-chain selector."""


class AgentCatalogAdministrationService:
    """Authorize catalog changes before reaching persistence."""

    def __init__(self, repository: AgentCatalogAdministrationRepository) -> None:
        """Configure tenant-safe persistence."""
        self._repository = repository

    @staticmethod
    def _require_admin(context: ExecutionContext) -> None:
        if not {
            OrganizationRole.OWNER.value,
            OrganizationRole.ORGANIZATION_ADMIN.value,
        }.intersection(context.role_codes):
            raise AdministrationDeniedError

    async def list_assignments(self, context: ExecutionContext) -> list[AgentAssignmentDetail]:
        """Show assignments only to an authorized organization administrator."""
        self._require_admin(context)
        return await self._repository.list_assignments(context.organization_id)

    async def list_catalog(self, context: ExecutionContext) -> list[AgentCatalogItem]:
        """Show catalog definitions and versions only to organization administrators."""
        self._require_admin(context)
        return await self._repository.list_catalog(context.organization_id)

    async def install(self, context: ExecutionContext, agent_code: str, version: str) -> None:
        """Install an agent version disabled by default."""
        self._require_admin(context)
        await self._repository.install(
            context.organization_id, agent_code, version, UUID(context.actor_id)
        )

    async def set_enabled(
        self, context: ExecutionContext, agent_code: str, *, enabled: bool
    ) -> bool:
        """Enable or disable an installed agent."""
        self._require_admin(context)
        return await self._repository.set_enabled(
            context.organization_id, agent_code, enabled=enabled
        )

    async def assign(self, context: ExecutionContext, command: AgentAssignmentInput) -> UUID:
        """Assign an agent to one supported organization relationship."""
        self._require_admin(context)
        if (
            command.target_type
            not in {"organization", "role", "department", "team", "project", "user"}
            or not command.actions
        ):
            raise AdministrationDeniedError
        return await self._repository.assign(
            context.organization_id, command, UUID(context.actor_id)
        )

    async def revoke_assignment(self, context: ExecutionContext, assignment_id: UUID) -> bool:
        """Revoke an assignment under the current server tenant."""
        self._require_admin(context)
        return await self._repository.revoke_assignment(context.organization_id, assignment_id)

    async def set_approval_chain(
        self, context: ExecutionContext, command: AgentApprovalChainInput
    ) -> UUID:
        """Configure an ordered, non-empty approval chain for an installed agent."""
        self._require_admin(context)
        if (
            command.risk not in {"low", "medium", "high", "critical"}
            or not command.target_system.strip()
            or not command.approver_steps
            or any(not step.strip() for step in command.approver_steps)
        ):
            raise AdministrationDeniedError
        return await self._repository.set_approval_chain(
            context.organization_id, command, UUID(context.actor_id)
        )
