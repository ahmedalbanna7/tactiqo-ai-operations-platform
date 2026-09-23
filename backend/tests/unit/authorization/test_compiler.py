"""Matrix and security tests for the unified policy compiler."""

from datetime import UTC, datetime

import pytest

from tactiqo.authorization.application.compiler import PolicyCompiler
from tactiqo.authorization.domain.models import (
    PolicyAction,
    PolicyDecision,
    PolicyEffect,
    PolicyObligation,
    PolicyObligationType,
    PolicyResource,
    PolicyRule,
)
from tactiqo.shared.domain.execution import ExecutionContext

EXPECTED_INVALIDATED_CACHE_ENTRIES = 2


class MemoryPolicyPorts:
    """Test repository, audit, and allow-only cache."""

    def __init__(self, rules: list[PolicyRule]) -> None:
        """Initialize rules and captures."""
        self.rules = rules
        self.audit: list[PolicyDecision] = []
        self.cache: dict[str, PolicyDecision] = {}
        self.rule_reads = 0

    async def list_rules(self, _organization_id: str, policy_version: str) -> list[PolicyRule]:
        """Return matching-version test rules."""
        self.rule_reads += 1
        return [rule for rule in self.rules if rule.policy_version == policy_version]

    async def record(
        self,
        _context: object,
        _resource: object,
        _action: str,
        decision: PolicyDecision,
    ) -> None:
        """Capture sanitized decisions."""
        self.audit.append(decision)

    async def get(self, key: str) -> PolicyDecision | None:
        """Load cached allow."""
        return self.cache.get(key)

    async def put(self, key: str, decision: PolicyDecision) -> None:
        """Cache allow decisions only."""
        assert decision.allowed
        self.cache[key] = decision


def _context(**overrides: object) -> ExecutionContext:
    values: dict[str, object] = {
        "actor_id": "employee-1",
        "organization_id": "org-a",
        "correlation_id": "correlation",
        "classification_clearance": "confidential",
        "policy_version": "v1",
        "department_ids": ("finance",),
        "team_ids": ("ap",),
        "project_ids": ("erp",),
        "role_codes": ("employee",),
        "data_region": "eg",
    }
    values.update(overrides)
    return ExecutionContext(**values)  # type: ignore[arg-type]


def _rule(effect: PolicyEffect = PolicyEffect.ALLOW, **overrides: object) -> PolicyRule:
    values: dict[str, object] = {
        "rule_id": f"{effect.value}-1",
        "policy_version": "v1",
        "effect": effect,
        "actions": frozenset({PolicyAction.VISIBLE, PolicyAction.USE}),
        "resource_types": frozenset({"agent"}),
        "role_codes": frozenset({"employee"}),
        "department_ids": frozenset({"finance"}),
        "classification_ceiling": "confidential",
    }
    values.update(overrides)
    return PolicyRule(**values)  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_matrix_requires_role_department_action_and_classification() -> None:
    """RBAC, ReBAC, action, and classification must all match."""
    ports = MemoryPolicyPorts([_rule()])
    compiler = PolicyCompiler(ports, ports, ports)
    resource = PolicyResource("agent", "finance", "org-a", "confidential", department_id="finance")
    assert (await compiler.decide(_context(), resource, PolicyAction.USE)).allowed
    assert not (
        await compiler.decide(_context(role_codes=("auditor",)), resource, PolicyAction.USE)
    ).allowed
    assert not (
        await compiler.decide(_context(department_ids=("it",)), resource, PolicyAction.USE)
    ).allowed
    restricted = PolicyResource("agent", "finance", "org-a", "restricted", department_id="finance")
    assert not (await compiler.decide(_context(), restricted, PolicyAction.USE)).allowed
    assert not (await compiler.decide(_context(), resource, PolicyAction.EXPORT)).allowed


@pytest.mark.anyio
async def test_explicit_deny_precedes_allow_and_is_not_cached() -> None:
    """Any matching explicit deny wins and deny results remain uncached."""
    ports = MemoryPolicyPorts([_rule(), _rule(PolicyEffect.DENY)])
    decision = await PolicyCompiler(ports, ports, ports).decide(
        _context(),
        PolicyResource("agent", "finance", "org-a", department_id="finance"),
        PolicyAction.USE,
    )
    assert not decision.allowed
    assert decision.reason_code == "explicit_deny"
    assert ports.cache == {}


@pytest.mark.anyio
async def test_approval_obligation_survives_compilation() -> None:
    """Allowed material actions retain their required human approval."""
    obligation = PolicyObligation(PolicyObligationType.APPROVAL, "finance-manager")
    ports = MemoryPolicyPorts([_rule(obligations=(obligation,))])
    decision = await PolicyCompiler(ports, ports, ports).decide(
        _context(),
        PolicyResource("agent", "finance", "org-a", department_id="finance"),
        PolicyAction.USE,
    )
    assert decision.obligations == (obligation,)


@pytest.mark.anyio
async def test_cache_key_invalidates_on_membership_or_policy_version_change() -> None:
    """Changed memberships or policy versions cannot reuse an earlier allow."""
    ports = MemoryPolicyPorts([_rule()])
    compiler = PolicyCompiler(ports, ports, ports)
    resource = PolicyResource("agent", "finance", "org-a", department_id="finance")
    await compiler.decide(_context(), resource, PolicyAction.USE)
    assert len(ports.cache) == 1
    await compiler.decide(_context(team_ids=("new-team",)), resource, PolicyAction.USE)
    assert len(ports.cache) == EXPECTED_INVALIDATED_CACHE_ENTRIES
    decision = await compiler.decide(_context(policy_version="v2"), resource, PolicyAction.USE)
    assert not decision.allowed


@pytest.mark.anyio
async def test_geography_time_owner_and_cross_tenant_conditions() -> None:
    """ABAC conditions and tenant boundary fail closed."""
    rule = _rule(
        department_ids=frozenset(),
        geography=frozenset({"eg"}),
        owner_only=True,
        utc_hour_start=8,
        utc_hour_end=17,
    )
    ports = MemoryPolicyPorts([rule])
    compiler = PolicyCompiler(ports, ports, ports)
    resource = PolicyResource(
        "agent", "owned", "org-a", owner_actor_id="employee-1", geography="eg"
    )
    assert (
        await compiler.decide(
            _context(), resource, PolicyAction.USE, datetime(2026, 1, 1, 9, tzinfo=UTC)
        )
    ).allowed
    assert not (
        await compiler.decide(
            _context(), resource, PolicyAction.USE, datetime(2026, 1, 1, 20, tzinfo=UTC)
        )
    ).allowed
    foreign = PolicyResource("agent", "owned", "org-b", owner_actor_id="employee-1", geography="eg")
    assert (
        await compiler.decide(_context(), foreign, PolicyAction.USE)
    ).reason_code == "scope_mismatch"


@pytest.mark.anyio
async def test_batch_decisions_read_rules_once_and_preserve_per_resource_results() -> None:
    """Catalog previews compile many agent actions from one tenant rule snapshot."""
    ports = MemoryPolicyPorts([_rule()])
    compiler = PolicyCompiler(ports, ports, ports)
    decisions = await compiler.decide_many(
        _context(),
        [
            (
                PolicyResource("agent", "finance", "org-a", department_id="finance"),
                PolicyAction.USE,
            ),
            (
                PolicyResource("agent", "foreign", "org-b", department_id="finance"),
                PolicyAction.USE,
            ),
        ],
    )
    assert [item.reason_code for item in decisions] == ["allowed", "scope_mismatch"]
    assert ports.rule_reads == 1
    assert ports.audit == decisions
