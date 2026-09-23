"""Read-only preview of the permissions effective for a tenant member."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from tactiqo.agents.catalog.application.service import AgentCatalogService
from tactiqo.agents.catalog.domain.models import EffectiveAgentCard
from tactiqo.authorization.application.ports import (
    AccessPreviewUnitReader,
    EffectiveToolAccessReader,
)
from tactiqo.authorization.domain.models import EffectiveToolGrantSummary, OrganizationUnitScope
from tactiqo.identity.application.administration import AdministrationDeniedError
from tactiqo.identity.application.context import ExecutionContextResolver
from tactiqo.identity.domain.models import OrganizationRole
from tactiqo.shared.domain.execution import ExecutionContext

UNSUPPORTED_ROLE = "unsupported_role"
UNSUPPORTED_OPERATION = "unsupported_operation"
UNCHANGED_SCENARIO = "scenario_unchanged"
UNSUPPORTED_MEMBERSHIP_SCOPE = "unsupported_membership_scope"
_ROLE_CODES = {role.value for role in OrganizationRole} - {"owner"}


@dataclass(frozen=True, slots=True)
class PreviewAgent:
    """One agent visible to a simulated employee, with allowed actions only."""

    code: str
    name: str
    category: str
    allowed_actions: tuple[str, ...]
    reason_code: str


@dataclass(frozen=True, slots=True)
class PreviewAgentActionChange:
    """One agent's action delta in a hypothetical role scenario."""

    code: str
    name: str
    gained_actions: tuple[str, ...]
    lost_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EffectiveAccessPreview:
    """Secret-free and explicitly read-only current-access preview."""

    user_id: UUID
    organization_id: str
    policy_version: str
    evaluated_at: datetime
    scope: str
    agents: tuple[PreviewAgent, ...]
    proposed_role: str | None = None
    role_operation: str | None = None
    proposed_agents: tuple[PreviewAgent, ...] = ()
    gained_agents: tuple[str, ...] = ()
    lost_agents: tuple[str, ...] = ()
    action_changes: tuple[PreviewAgentActionChange, ...] = ()
    tool_grants: tuple[EffectiveToolGrantSummary, ...] = ()
    tools_truncated: bool = False
    proposed_scope_kind: str | None = None
    proposed_scope_id: str | None = None
    scope_operation: str | None = None


@dataclass(frozen=True, slots=True)
class AccessPreviewScenario:
    """One mutually exclusive hypothetical role or organization-scope change."""

    role_code: str | None = None
    role_operation: str | None = None
    scope_kind: str | None = None
    scope_id: str | None = None
    scope_operation: str | None = None

    @property
    def has_role(self) -> bool:
        """Whether this scenario simulates a role change."""
        return self.role_code is not None

    @property
    def has_scope(self) -> bool:
        """Whether this scenario simulates a department/team/project change."""
        return any(
            value is not None
            for value in (self.scope_kind, self.scope_id, self.scope_operation)
        )


class EffectiveAccessPreviewService:
    """Resolve a target as a standard employee; never impersonate or execute actions."""

    def __init__(
        self,
        contexts: ExecutionContextResolver,
        agents: AgentCatalogService,
        tool_access: EffectiveToolAccessReader | None = None,
        unit_reader: AccessPreviewUnitReader | None = None,
    ) -> None:
        """Configure trusted context resolution and the live policy-backed catalog."""
        self._contexts = contexts
        self._agents = agents
        self._tool_access = tool_access
        self._unit_reader = unit_reader

    async def preview(
        self,
        administrator: ExecutionContext,
        user_id: UUID,
        scenario: AccessPreviewScenario | None = None,
    ) -> EffectiveAccessPreview:
        """Compare current and hypothetical role/scope agent access without writes."""
        scenario = scenario or AccessPreviewScenario()
        if not {
            OrganizationRole.OWNER.value,
            OrganizationRole.ORGANIZATION_ADMIN.value,
        }.intersection(administrator.role_codes):
            raise AdministrationDeniedError
        self._validate_scenario(scenario)
        target = await self._contexts.resolve_delegated(
            str(user_id), administrator.organization_id,
            administrator.correlation_id, "standard",
        )
        if target is None:
            unavailable = "member_not_available"
            raise LookupError(unavailable)
        simulated_target = await self._apply_scenario(
            administrator.organization_id, target, scenario
        )
        cards = await self._agents.effective_cards(target)
        tool_grants, tools_truncated = await self._read_tool_grants(target)
        proposed_cards = (
            await self._agents.effective_cards(simulated_target)
            if simulated_target != target
            else []
        )
        gained, lost, action_changes = self._compare(cards, proposed_cards)
        return EffectiveAccessPreview(
            user_id=user_id,
            organization_id=administrator.organization_id,
            policy_version=target.policy_version,
            evaluated_at=datetime.now(UTC),
            scope=self._result_scope(scenario),
            agents=tuple(self._preview_agent(card) for card in cards),
            proposed_role=scenario.role_code,
            role_operation=scenario.role_operation,
            proposed_agents=tuple(self._preview_agent(card) for card in proposed_cards),
            gained_agents=gained,
            lost_agents=lost,
            action_changes=action_changes,
            tool_grants=tuple(tool_grants),
            tools_truncated=tools_truncated,
            proposed_scope_kind=scenario.scope_kind,
            proposed_scope_id=scenario.scope_id,
            scope_operation=scenario.scope_operation,
        )

    def _validate_scenario(self, scenario: AccessPreviewScenario) -> None:
        """Reject malformed or conflicting scenarios before resolving the target member."""
        if (scenario.role_code is None) != (scenario.role_operation is None):
            raise ValueError(UNSUPPORTED_OPERATION)
        if scenario.has_role and scenario.role_code not in _ROLE_CODES:
            raise ValueError(UNSUPPORTED_ROLE)
        if scenario.has_role and scenario.role_operation not in {"add", "remove"}:
            raise ValueError(UNSUPPORTED_OPERATION)
        values = (scenario.scope_kind, scenario.scope_id, scenario.scope_operation)
        if scenario.has_scope and any(value is None for value in values):
            raise ValueError(UNSUPPORTED_MEMBERSHIP_SCOPE)
        if scenario.has_scope and scenario.has_role:
            raise ValueError(UNSUPPORTED_MEMBERSHIP_SCOPE)
        if scenario.has_scope and (
            scenario.scope_kind not in {"department", "team", "project"}
            or scenario.scope_operation not in {"add", "remove"}
            or self._unit_reader is None
        ):
            raise ValueError(UNSUPPORTED_MEMBERSHIP_SCOPE)

    async def _apply_scenario(
        self, organization_id: str, target: ExecutionContext, scenario: AccessPreviewScenario
    ) -> ExecutionContext:
        """Return the target context with exactly one validated hypothetical change."""
        if scenario.has_role and scenario.role_code is not None:
            roles = set(target.role_codes)
            if (scenario.role_operation == "add") == (scenario.role_code in roles):
                raise ValueError(UNCHANGED_SCENARIO)
            roles.symmetric_difference_update({scenario.role_code})
            return replace(target, role_codes=tuple(sorted(roles)))
        if scenario.has_scope:
            if (
                self._unit_reader is None
                or scenario.scope_kind is None
                or scenario.scope_id is None
                or scenario.scope_operation is None
            ):
                raise ValueError(UNSUPPORTED_MEMBERSHIP_SCOPE)
            unit = await self._unit_reader.read_unit(
                organization_id, scenario.scope_kind, scenario.scope_id
            )
            if unit is None:
                raise ValueError(UNSUPPORTED_MEMBERSHIP_SCOPE)
            return self._simulate_membership(target, unit, scenario.scope_operation)
        return target

    async def _read_tool_grants(
        self, target: ExecutionContext
    ) -> tuple[list[EffectiveToolGrantSummary], bool]:
        """Read the current-state grants only; scenarios do not rewrite tool scope."""
        if self._tool_access is None:
            return [], False
        return await self._tool_access.read(target)

    @staticmethod
    def _compare(
        current: list[EffectiveAgentCard], proposed: list[EffectiveAgentCard]
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[PreviewAgentActionChange, ...]]:
        """Build gained/lost agent and action deltas from two policy-filtered lists."""
        current_by_code = {card.code: card for card in current}
        proposed_by_code = {card.code: card for card in proposed}
        changes = tuple(
            PreviewAgentActionChange(
                code=card.code,
                name=card.name,
                gained_actions=tuple(sorted(
                    action.value
                    for action in proposed_by_code[card.code].allowed_actions
                    if action not in card.allowed_actions
                )),
                lost_actions=tuple(sorted(
                    action.value
                    for action in card.allowed_actions
                    if action not in proposed_by_code[card.code].allowed_actions
                )),
            )
            for card in current
            if card.code in proposed_by_code
            and set(card.allowed_actions) != set(proposed_by_code[card.code].allowed_actions)
        )
        return (
            tuple(sorted(proposed_by_code.keys() - current_by_code.keys())),
            tuple(sorted(current_by_code.keys() - proposed_by_code.keys())),
            changes,
        )

    @staticmethod
    def _result_scope(scenario: AccessPreviewScenario) -> str:
        """Name the scenario type explicitly for the UI and audit consumers."""
        if scenario.has_scope:
            return "membership_change_agent_access_simulation"
        if scenario.has_role:
            return "role_change_agent_access_simulation"
        return "current_agent_access"

    @staticmethod
    def _simulate_membership(
        target: ExecutionContext, scope: OrganizationUnitScope, operation: str
    ) -> ExecutionContext:
        """Apply one validated hypothetical membership to an immutable employee context."""
        if operation not in {"add", "remove"}:
            raise ValueError(UNSUPPORTED_MEMBERSHIP_SCOPE)
        if scope.kind == "department":
            departments = EffectiveAccessPreviewService._change_membership(
                target.department_ids, scope.unit_id, operation
            )
            team_ids = target.team_ids
            project_ids = target.project_ids
            if operation == "remove":
                team_ids = tuple(
                    value for value in team_ids if value not in scope.descendant_team_ids
                )
                project_ids = tuple(
                    value for value in project_ids if value not in scope.descendant_project_ids
                )
            return replace(
                target,
                department_ids=departments,
                organizational_unit_ids=departments,
                team_ids=team_ids,
                project_ids=project_ids,
            )
        if scope.kind in {"team", "project"}:
            if operation == "add" and scope.department_id not in target.department_ids:
                raise ValueError(UNSUPPORTED_MEMBERSHIP_SCOPE)
            if scope.kind == "team":
                return replace(
                    target,
                    team_ids=EffectiveAccessPreviewService._change_membership(
                        target.team_ids, scope.unit_id, operation
                    ),
                )
            return replace(
                target,
                project_ids=EffectiveAccessPreviewService._change_membership(
                    target.project_ids, scope.unit_id, operation
                ),
            )
        raise ValueError(UNSUPPORTED_MEMBERSHIP_SCOPE)

    @staticmethod
    def _change_membership(
        values: tuple[str, ...], unit_id: str, operation: str
    ) -> tuple[str, ...]:
        """Add or remove one member ID, rejecting no-op scenarios explicitly."""
        current = set(values)
        if (operation == "add") == (unit_id in current):
            raise ValueError(UNCHANGED_SCENARIO)
        current.symmetric_difference_update({unit_id})
        return tuple(sorted(current))

    @staticmethod
    def _preview_agent(card: EffectiveAgentCard) -> PreviewAgent:
        """Project only permitted metadata and actions into the preview response."""
        return PreviewAgent(
            code=card.code,
            name=card.name,
            category=card.category.value,
            allowed_actions=tuple(action.value for action in card.allowed_actions),
            reason_code="allowed",
        )
