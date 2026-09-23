"""Hidden discovery and direct invocation tests."""

import pytest

from tactiqo.agents.catalog.application.service import AgentCatalogService
from tactiqo.agents.catalog.domain.models import (
    AgentCandidate,
    AgentCategory,
    AgentDefinition,
    AgentRisk,
    AgentVersion,
)
from tactiqo.authorization.application.compiler import PolicyCompiler
from tactiqo.authorization.domain.models import PolicyAction, PolicyEffect, PolicyRule
from tactiqo.shared.domain.execution import ExecutionContext
from tests.unit.authorization.test_compiler import MemoryPolicyPorts


class MemoryCatalog:
    """Mutable catalog used to simulate assignment revocation."""

    def __init__(self, candidates: list[AgentCandidate]) -> None:
        """Initialize visible candidates."""
        self.candidates = candidates

    async def list_candidates(self, _organization_id: str) -> list[AgentCandidate]:
        """Return installed test candidates."""
        return self.candidates

    async def get_candidate(self, _organization_id: str, agent_code: str) -> AgentCandidate | None:
        """Return only an exact installed candidate."""
        return next((item for item in self.candidates if item.definition.code == agent_code), None)


def _candidate(code: str) -> AgentCandidate:
    definition = AgentDefinition(code, code.title(), "Safe description", AgentCategory.BUSINESS)
    version = AgentVersion(code, "1", "template-v1", {}, ("report",), {}, {}, AgentRisk.LOW)
    return AgentCandidate(definition, version, department_id="finance")


def _context() -> ExecutionContext:
    return ExecutionContext(
        "employee-1",
        "org-a",
        "correlation",
        "confidential",
        "v1",
        department_ids=("finance",),
        role_codes=("employee",),
    )


def _allow_rule(agent_code: str) -> PolicyRule:
    return PolicyRule(
        f"allow-{agent_code}",
        "v1",
        PolicyEffect.ALLOW,
        frozenset({PolicyAction.VISIBLE, PolicyAction.USE}),
        frozenset({"agent"}),
        resource_ids=frozenset({agent_code}),
        role_codes=frozenset({"employee"}),
        department_ids=frozenset({"finance"}),
    )


@pytest.mark.anyio
async def test_employee_receives_only_effective_agent_cards() -> None:
    """Hidden agent metadata never crosses the application boundary."""
    catalog = MemoryCatalog([_candidate("finance"), _candidate("legal")])
    ports = MemoryPolicyPorts([_allow_rule("finance")])
    cards = await AgentCatalogService(catalog, PolicyCompiler(ports, ports, ports)).effective_cards(
        _context()
    )
    assert [card.code for card in cards] == ["finance"]
    assert cards[0].allowed_actions == (PolicyAction.USE,)


@pytest.mark.anyio
async def test_hidden_agent_direct_invocation_returns_not_found_shape() -> None:
    """Direct invocation does not reveal whether a denied agent exists."""
    catalog = MemoryCatalog([_candidate("legal")])
    ports = MemoryPolicyPorts([])
    result = await AgentCatalogService(
        catalog, PolicyCompiler(ports, ports, ports)
    ).authorize_invocation(_context(), "legal")
    assert result is None


@pytest.mark.anyio
async def test_assignment_revocation_is_rechecked_before_next_use() -> None:
    """Removing current rules blocks the next invocation despite prior access."""
    catalog = MemoryCatalog([_candidate("finance")])
    ports = MemoryPolicyPorts([_allow_rule("finance")])
    service = AgentCatalogService(catalog, PolicyCompiler(ports, ports, ports))
    assert await service.authorize_invocation(_context(), "finance") is not None
    ports.rules.clear()
    ports.cache.clear()
    assert await service.authorize_invocation(_context(), "finance") is None
