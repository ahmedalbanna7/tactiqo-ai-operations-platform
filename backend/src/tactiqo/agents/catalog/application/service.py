"""Effective agent discovery and guarded direct invocation."""

from typing import Protocol

from tactiqo.agents.catalog.domain.models import AgentCandidate, EffectiveAgentCard
from tactiqo.authorization.application.compiler import PolicyCompiler
from tactiqo.authorization.domain.models import PolicyAction, PolicyResource
from tactiqo.shared.domain.execution import ExecutionContext


class AgentCatalogRepository(Protocol):
    """Return installed candidates without exposing them to transport code."""

    async def list_candidates(self, organization_id: str) -> list[AgentCandidate]:
        """Load enabled organization agents and active versions."""

    async def get_candidate(self, organization_id: str, agent_code: str) -> AgentCandidate | None:
        """Load one candidate with exact tenant predicates."""


class AgentCatalogService:
    """Compile only visible cards and re-check every direct use."""

    def __init__(self, repository: AgentCatalogRepository, compiler: PolicyCompiler) -> None:
        """Configure catalog truth and unified policy authority."""
        self._repository = repository
        self._compiler = compiler

    async def effective_cards(self, context: ExecutionContext) -> list[EffectiveAgentCard]:
        """Return no metadata for agents whose visibility is denied."""
        candidates = await self._repository.list_candidates(context.organization_id)
        resources = [self._resource(context.organization_id, candidate) for candidate in candidates]
        visible_decisions = await self._compiler.decide_many(
            context,
            [(resource, PolicyAction.VISIBLE) for resource in resources],
        )
        visible_candidates = [
            (candidate, resource, decision)
            for candidate, resource, decision in zip(
                candidates, resources, visible_decisions, strict=True
            )
            if decision.allowed
        ]
        requested_actions = [
            (resource, action)
            for _, resource, _ in visible_candidates
            for action in PolicyAction
            if action is not PolicyAction.VISIBLE
        ]
        action_decisions = iter(await self._compiler.decide_many(context, requested_actions))
        cards: list[EffectiveAgentCard] = []
        for candidate, _, visible in visible_candidates:
            allowed: list[PolicyAction] = []
            obligations = list(visible.obligations)
            for action in PolicyAction:
                if action is PolicyAction.VISIBLE:
                    continue
                decision = next(action_decisions)
                if decision.allowed:
                    allowed.append(action)
                    obligations.extend(decision.obligations)
            cards.append(
                EffectiveAgentCard(
                    candidate.definition.code,
                    candidate.definition.name,
                    candidate.definition.description,
                    candidate.definition.category,
                    candidate.version.version,
                    candidate.version.capabilities,
                    tuple(allowed),
                    tuple(dict.fromkeys(obligations)),
                )
            )
        return cards

    async def authorize_invocation(
        self,
        context: ExecutionContext,
        agent_code: str,
        action: PolicyAction = PolicyAction.USE,
    ) -> EffectiveAgentCard | None:
        """Re-evaluate current assignment and hide denied direct invocations."""
        candidate = await self._repository.get_candidate(context.organization_id, agent_code)
        if candidate is None:
            return None
        resource = self._resource(context.organization_id, candidate)
        visible = await self._compiler.decide(context, resource, PolicyAction.VISIBLE)
        decision = await self._compiler.decide(context, resource, action)
        if not visible.allowed or not decision.allowed:
            return None
        return EffectiveAgentCard(
            candidate.definition.code,
            candidate.definition.name,
            candidate.definition.description,
            candidate.definition.category,
            candidate.version.version,
            candidate.version.capabilities,
            (action,),
            tuple(dict.fromkeys((*visible.obligations, *decision.obligations))),
        )

    @staticmethod
    def _resource(organization_id: str, candidate: AgentCandidate) -> PolicyResource:
        return PolicyResource(
            "agent",
            candidate.definition.code,
            organization_id,
            candidate.classification,
            department_id=candidate.department_id,
            team_id=candidate.team_id,
            project_id=candidate.project_id,
        )
