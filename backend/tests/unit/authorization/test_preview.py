"""Current-access preview authorization and non-impersonation tests."""

from dataclasses import replace
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

from tactiqo.agents.catalog.domain.models import AgentCategory, EffectiveAgentCard
from tactiqo.authorization.application.preview import (
    AccessPreviewScenario,
    EffectiveAccessPreviewService,
)
from tactiqo.authorization.domain.models import (
    EffectiveToolGrantSummary,
    OrganizationUnitScope,
    PolicyAction,
)
from tactiqo.identity.application.administration import AdministrationDeniedError
from tactiqo.identity.domain.models import OrganizationRole
from tactiqo.shared.domain.execution import ExecutionContext

CURRENT_ACCESS_EVALUATIONS = 1
ROLE_SIMULATION_EVALUATIONS = 2

if TYPE_CHECKING:
    from tactiqo.agents.catalog.application.service import AgentCatalogService
    from tactiqo.authorization.application.ports import (
        AccessPreviewUnitReader,
        EffectiveToolAccessReader,
    )


class FakeContexts:
    """Capture delegated context requests and return a target context."""

    def __init__(self, target: ExecutionContext) -> None:
        """Store one resolved target context for delegation tests."""
        self.target = target
        self.calls: list[tuple[str, str, str, str]] = []

    async def resolve(self, opaque_session: str, correlation_id: str) -> None:
        """Browser authentication is not used by this internal preview test."""
        _ = opaque_session, correlation_id

    async def resolve_delegated(
        self, actor_id: str, organization_id: str, correlation_id: str, session_assurance: str
    ) -> ExecutionContext:
        """Record the exact server-derived delegation request."""
        self.calls.append((actor_id, organization_id, correlation_id, session_assurance))
        return self.target


class FakeAgents:
    """Return only the agent cards the policy compiler allowed."""

    def __init__(self) -> None:
        """Track policy evaluations to prevent duplicate preview work."""
        self.calls = 0
        self.contexts: list[ExecutionContext] = []

    async def effective_cards(self, context: ExecutionContext) -> list[EffectiveAgentCard]:
        """Return one authorized agent and assert standard employee assurance."""
        self.calls += 1
        self.contexts.append(context)
        assert context.session_assurance == "standard"
        cards = [
            EffectiveAgentCard(
                "project_manager", "Project Manager", "description", AgentCategory.BUSINESS, "1",
                ("read",), (PolicyAction.VISIBLE, PolicyAction.USE), (),
            )
        ]
        if "organization_admin" in context.role_codes:
            cards[0] = replace(
                cards[0],
                allowed_actions=(*cards[0].allowed_actions, PolicyAction.ADMINISTER),
            )
            cards.append(
                EffectiveAgentCard(
                    "settings_admin", "Settings Admin", "description", AgentCategory.BUSINESS,
                    "1", ("administer",), (PolicyAction.VISIBLE, PolicyAction.ADMINISTER), (),
                )
            )
        if "department-a" in context.department_ids:
            cards.append(
                EffectiveAgentCard(
                    "department_agent", "Department Agent", "description",
                    AgentCategory.BUSINESS, "1", ("read",),
                    (PolicyAction.VISIBLE, PolicyAction.USE), (),
                )
            )
        if "team-a" in context.team_ids:
            cards.append(
                EffectiveAgentCard(
                    "team_agent", "Team Agent", "description", AgentCategory.BUSINESS,
                    "1", ("read",), (PolicyAction.VISIBLE, PolicyAction.USE), (),
                )
            )
        if "project-a" in context.project_ids:
            cards.append(
                EffectiveAgentCard(
                    "scoped_project_agent", "Scoped Project Agent", "description",
                    AgentCategory.BUSINESS, "1", ("read",),
                    (PolicyAction.VISIBLE, PolicyAction.USE), (),
                )
            )
        return cards


class FakeUnitReader:
    """Resolve only an explicitly configured organization unit in tests."""

    def __init__(self, scope: OrganizationUnitScope | None) -> None:
        """Store one allowed lookup result and capture tenant predicates."""
        self.scope = scope
        self.calls: list[tuple[str, str, str]] = []

    async def read_unit(
        self, organization_id: str, kind: str, unit_id: str
    ) -> OrganizationUnitScope | None:
        """Record the tenant and unit identity presented to the lookup port."""
        self.calls.append((organization_id, kind, unit_id))
        if self.scope is None or (self.scope.kind, self.scope.unit_id) != (kind, unit_id):
            return None
        return self.scope


class FakeToolAccessReader:
    """Return one target-specific capability without any provider I/O."""

    async def read(
        self, context: ExecutionContext
    ) -> tuple[list[EffectiveToolGrantSummary], bool]:
        """Return a secret-free configured grant for the resolved employee."""
        assert context.actor_id == "target-user"
        assert context.session_assurance == "standard"
        return [EffectiveToolGrantSummary("jira", "company-jira", "jira_search", "read")], False


def context(actor: str, *roles: str, assurance: str = "step_up") -> ExecutionContext:
    """Construct an immutable actor context for policy assertions."""
    return ExecutionContext(
        actor_id=actor,
        organization_id="tenant-a",
        correlation_id="correlation-a",
        classification_clearance="internal",
        policy_version="version-3",
        role_codes=roles,
        session_assurance=assurance,
    )


@pytest.mark.anyio
async def test_preview_resolves_current_target_at_standard_assurance() -> None:
    """Preview uses target's current server context and returns allowed-only metadata."""
    target_id = uuid4()
    resolver = FakeContexts(context(str(target_id), "employee", assurance="standard"))
    agents = FakeAgents()
    service = EffectiveAccessPreviewService(resolver, cast("AgentCatalogService", agents))
    result = await service.preview(context(str(uuid4()), OrganizationRole.OWNER.value), target_id)
    assert resolver.calls == [(str(target_id), "tenant-a", "correlation-a", "standard")]
    assert result.scope == "current_agent_access"
    assert result.policy_version == "version-3"
    assert [agent.code for agent in result.agents] == ["project_manager"]
    assert result.agents[0].reason_code == "allowed"
    assert result.proposed_agents == ()
    assert agents.calls == CURRENT_ACCESS_EVALUATIONS


@pytest.mark.anyio
async def test_preview_compares_a_temporary_role_change_without_writing() -> None:
    """A hypothetical role is applied only to an immutable, standard-assurance context."""
    target_id = uuid4()
    resolver = FakeContexts(context(str(target_id), "employee", assurance="standard"))
    agents = FakeAgents()
    service = EffectiveAccessPreviewService(resolver, cast("AgentCatalogService", agents))
    result = await service.preview(
        context(str(uuid4()), OrganizationRole.OWNER.value),
        target_id,
        AccessPreviewScenario(role_code="organization_admin", role_operation="add"),
    )
    assert [item.code for item in result.agents] == ["project_manager"]
    assert [item.code for item in result.proposed_agents] == ["project_manager", "settings_admin"]
    assert result.gained_agents == ("settings_admin",)
    assert result.lost_agents == ()
    assert len(result.action_changes) == 1
    assert result.action_changes[0].code == "project_manager"
    assert result.action_changes[0].gained_actions == (PolicyAction.ADMINISTER.value,)
    assert result.action_changes[0].lost_actions == ()
    assert agents.calls == ROLE_SIMULATION_EVALUATIONS
    assert result.scope == "role_change_agent_access_simulation"
    assert resolver.calls == [(str(target_id), "tenant-a", "correlation-a", "standard")]


@pytest.mark.anyio
async def test_non_admin_cannot_probe_member_access() -> None:
    """A denial happens before target resolution, avoiding an existence oracle."""
    resolver = FakeContexts(context(str(uuid4()), "employee", assurance="standard"))
    service = EffectiveAccessPreviewService(resolver, cast("AgentCatalogService", FakeAgents()))
    with pytest.raises(AdministrationDeniedError):
        await service.preview(context(str(uuid4()), "employee"), uuid4())
    assert resolver.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("proposed_role", "role_operation"),
    [("employee", None), (None, "add"), ("owner", "add"), ("employee", "merge")],
)
async def test_invalid_role_scenario_is_rejected_before_target_lookup(
    proposed_role: str | None, role_operation: str | None
) -> None:
    """Malformed scenarios cannot trigger target resolution or policy/database work."""
    resolver = FakeContexts(context("target-user", "employee", assurance="standard"))
    agents = FakeAgents()
    service = EffectiveAccessPreviewService(resolver, cast("AgentCatalogService", agents))

    with pytest.raises(ValueError, match="unsupported_(role|operation)"):
        await service.preview(
            context("admin-user", OrganizationRole.OWNER.value),
            uuid4(),
            AccessPreviewScenario(
                role_code=proposed_role, role_operation=role_operation
            ),
        )

    assert resolver.calls == []
    assert agents.calls == 0


@pytest.mark.anyio
async def test_team_membership_addition_simulates_only_agent_policy_access() -> None:
    """A validated team is added to a copy of the employee context, never persisted."""
    target_id = uuid4()
    resolver = FakeContexts(
        replace(
            context(str(target_id), "employee", assurance="standard"),
            department_ids=("department-a",),
        )
    )
    agents = FakeAgents()
    reader = FakeUnitReader(OrganizationUnitScope("team", "team-a", "department-a"))
    service = EffectiveAccessPreviewService(
        resolver,
        cast("AgentCatalogService", agents),
        unit_reader=cast("AccessPreviewUnitReader", reader),
    )

    result = await service.preview(
        context("admin-user", OrganizationRole.OWNER.value),
        target_id,
        AccessPreviewScenario(scope_kind="team", scope_id="team-a", scope_operation="add"),
    )

    assert result.scope == "membership_change_agent_access_simulation"
    assert result.proposed_scope_kind == "team"
    assert result.proposed_scope_id == "team-a"
    assert result.gained_agents == ("team_agent",)
    assert reader.calls == [("tenant-a", "team", "team-a")]
    assert resolver.target.team_ids == ()
    assert agents.contexts[-1].team_ids == ("team-a",)


@pytest.mark.anyio
async def test_department_removal_removes_descendant_scopes_only_in_simulation() -> None:
    """Removing a department also hides its child scopes without mutating current context."""
    target_id = uuid4()
    target = context(str(target_id), "employee", assurance="standard")
    target = replace(
        target,
        department_ids=("department-a", "department-b"),
        organizational_unit_ids=("department-a", "department-b"),
        team_ids=("team-a", "team-b"),
        project_ids=("project-a", "project-b"),
    )
    resolver = FakeContexts(target)
    agents = FakeAgents()
    reader = FakeUnitReader(
        OrganizationUnitScope(
            "department", "department-a", "department-a", ("team-a",), ("project-a",)
        )
    )
    service = EffectiveAccessPreviewService(
        resolver,
        cast("AgentCatalogService", agents),
        unit_reader=cast("AccessPreviewUnitReader", reader),
    )

    result = await service.preview(
        context("admin-user", OrganizationRole.OWNER.value),
        target_id,
        AccessPreviewScenario(
            scope_kind="department", scope_id="department-a", scope_operation="remove"
        ),
    )

    assert set(result.lost_agents) == {
        "department_agent", "team_agent", "scoped_project_agent"
    }
    assert resolver.target.department_ids == ("department-a", "department-b")
    assert agents.contexts[-1].department_ids == ("department-b",)
    assert agents.contexts[-1].team_ids == ("team-b",)
    assert agents.contexts[-1].project_ids == ("project-b",)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kind", "operation", "current_values", "expected_delta"),
    [
        ("team", "remove", ("team-a",), ("team_agent",)),
        ("project", "add", (), ("scoped_project_agent",)),
        ("project", "remove", ("project-a",), ("scoped_project_agent",)),
    ],
)
async def test_team_and_project_membership_scenarios_are_scoped_and_read_only(
    kind: str,
    operation: str,
    current_values: tuple[str, ...],
    expected_delta: tuple[str, ...],
) -> None:
    """A team/project change applies only to the selected unit under a joined department."""
    target_id = uuid4()
    target = replace(
        context(str(target_id), "employee", assurance="standard"),
        department_ids=("department-a",),
        team_ids=current_values if kind == "team" else (),
        project_ids=current_values if kind == "project" else (),
    )
    resolver = FakeContexts(target)
    agents = FakeAgents()
    reader = FakeUnitReader(OrganizationUnitScope(kind, f"{kind}-a", "department-a"))
    service = EffectiveAccessPreviewService(
        resolver,
        cast("AgentCatalogService", agents),
        unit_reader=cast("AccessPreviewUnitReader", reader),
    )

    result = await service.preview(
        context("admin-user", OrganizationRole.OWNER.value),
        target_id,
        AccessPreviewScenario(
            scope_kind=kind, scope_id=f"{kind}-a", scope_operation=operation
        ),
    )

    if operation == "add":
        assert result.gained_agents == expected_delta
        assert result.lost_agents == ()
    else:
        assert result.lost_agents == expected_delta
        assert result.gained_agents == ()
    assert resolver.target == target
    assert reader.calls == [("tenant-a", kind, f"{kind}-a")]


@pytest.mark.anyio
async def test_membership_addition_requires_existing_department_membership() -> None:
    """A manager cannot simulate access to a child scope under another department."""
    target_id = uuid4()
    resolver = FakeContexts(context(str(target_id), "employee", assurance="standard"))
    agents = FakeAgents()
    reader = FakeUnitReader(OrganizationUnitScope("project", "project-a", "department-a"))
    service = EffectiveAccessPreviewService(
        resolver,
        cast("AgentCatalogService", agents),
        unit_reader=cast("AccessPreviewUnitReader", reader),
    )

    with pytest.raises(ValueError, match="unsupported_membership_scope"):
        await service.preview(
            context("admin-user", OrganizationRole.OWNER.value),
            target_id,
            AccessPreviewScenario(
                scope_kind="project", scope_id="project-a", scope_operation="add"
            ),
        )

    assert agents.calls == 0
    assert resolver.target.project_ids == ()


@pytest.mark.anyio
async def test_preview_includes_secret_free_effective_tool_grants() -> None:
    """The access preview reads target grants using only a server-resolved context."""
    target_id = uuid4()
    resolver = FakeContexts(context("target-user", "employee", assurance="standard"))
    service = EffectiveAccessPreviewService(
        resolver,
        cast("AgentCatalogService", FakeAgents()),
        cast("EffectiveToolAccessReader", FakeToolAccessReader()),
    )

    result = await service.preview(context("admin-user", OrganizationRole.OWNER.value), target_id)

    assert result.tool_grants == (
        EffectiveToolGrantSummary("jira", "company-jira", "jira_search", "read"),
    )
    assert result.tools_truncated is False
