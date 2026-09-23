"""SQL policy truth, sanitized audit, and bounded safe decision cache."""

import hashlib
import json
import time
from collections.abc import Sequence

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.agents.catalog.infrastructure.tables import (
    AgentActionGrantRow,
    AgentAssignmentRow,
)
from tactiqo.authorization.domain.models import (
    PolicyAction,
    PolicyDecision,
    PolicyEffect,
    PolicyObligation,
    PolicyObligationType,
    PolicyResource,
    PolicyRule,
)
from tactiqo.authorization.infrastructure.tables import PolicyDecisionAuditRow, PolicyRuleRow
from tactiqo.shared.domain.execution import ExecutionContext


class SqlPolicyRepository:
    """Load active rules under exact tenant and version predicates."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure transaction factory."""
        self._sessions = sessions

    async def list_rules(self, organization_id: str, policy_version: str) -> list[PolicyRule]:
        """Map persistence rows into immutable domain rules."""
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(PolicyRuleRow).where(
                        PolicyRuleRow.organization_id == organization_id,
                        PolicyRuleRow.policy_version == policy_version,
                        PolicyRuleRow.active.is_(True),
                    )
                )
            ).all()
            assignment_rows = (
                await session.execute(
                    select(AgentAssignmentRow, AgentActionGrantRow)
                    .join(
                        AgentActionGrantRow,
                        and_(
                            AgentActionGrantRow.organization_id
                            == AgentAssignmentRow.organization_id,
                            AgentActionGrantRow.assignment_id == AgentAssignmentRow.id,
                        ),
                    )
                    .where(
                        AgentAssignmentRow.organization_id == organization_id,
                        AgentAssignmentRow.active.is_(True),
                    )
                )
            ).all()
        return [self._map(row) for row in rows] + [
            self._map_assignment(assignment, grant, policy_version)
            for assignment, grant in assignment_rows
        ]

    @staticmethod
    def _map(row: PolicyRuleRow) -> PolicyRule:
        obligations = tuple(
            PolicyObligation(PolicyObligationType(item["kind"]), item["value"])
            for item in json.loads(row.obligations_json)
        )
        return PolicyRule(
            rule_id=str(row.id),
            policy_version=row.policy_version,
            effect=PolicyEffect(row.effect),
            actions=frozenset(PolicyAction(value) for value in json.loads(row.actions_json)),
            resource_types=frozenset(json.loads(row.resource_types_json)),
            resource_ids=frozenset(json.loads(row.resource_ids_json)),
            role_codes=frozenset(json.loads(row.role_codes_json)),
            actor_ids=frozenset(json.loads(row.actor_ids_json)),
            department_ids=frozenset(json.loads(row.department_ids_json)),
            team_ids=frozenset(json.loads(row.team_ids_json)),
            project_ids=frozenset(json.loads(row.project_ids_json)),
            geography=frozenset(json.loads(row.geography_json)),
            classification_ceiling=row.classification_ceiling,
            owner_only=row.owner_only,
            utc_hour_start=row.utc_hour_start,
            utc_hour_end=row.utc_hour_end,
            obligations=obligations,
        )

    @staticmethod
    def _map_assignment(
        assignment: AgentAssignmentRow,
        grant: AgentActionGrantRow,
        policy_version: str,
    ) -> PolicyRule:
        """Compile one relationship assignment into a normal policy rule."""
        role_codes: frozenset[str] = frozenset()
        actor_ids: frozenset[str] = frozenset()
        department_ids: frozenset[str] = frozenset()
        team_ids: frozenset[str] = frozenset()
        project_ids: frozenset[str] = frozenset()
        subject_department_ids: frozenset[str] = frozenset()
        subject_team_ids: frozenset[str] = frozenset()
        subject_project_ids: frozenset[str] = frozenset()
        target_field = {
            "role": "role_codes",
            "user": "actor_ids",
            "department": "department_ids",
            "team": "team_ids",
            "project": "project_ids",
        }.get(assignment.target_type)
        if target_field == "role_codes":
            role_codes = frozenset({assignment.target_id})
        elif target_field == "actor_ids":
            actor_ids = frozenset({assignment.target_id})
        elif target_field == "department_ids":
            subject_department_ids = frozenset({assignment.target_id})
        elif target_field == "team_ids":
            subject_team_ids = frozenset({assignment.target_id})
        elif target_field == "project_ids":
            subject_project_ids = frozenset({assignment.target_id})
        obligations = tuple(
            PolicyObligation(PolicyObligationType(item["kind"]), item["value"])
            for item in json.loads(grant.obligations_json)
        )
        return PolicyRule(
            rule_id=f"assignment:{assignment.id}:{grant.action}",
            policy_version=policy_version,
            effect=PolicyEffect(grant.effect),
            actions=frozenset({PolicyAction(grant.action)}),
            resource_types=frozenset({"agent"}),
            resource_ids=frozenset({assignment.agent_code}),
            classification_ceiling=assignment.classification_ceiling,
            obligations=obligations,
            role_codes=role_codes,
            actor_ids=actor_ids,
            department_ids=department_ids,
            team_ids=team_ids,
            project_ids=project_ids,
            subject_department_ids=subject_department_ids,
            subject_team_ids=subject_team_ids,
            subject_project_ids=subject_project_ids,
        )


class SqlDecisionAudit:
    """Persist hashed resource identifiers and sanitized decision metadata."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure transaction factory."""
        self._sessions = sessions

    async def record(
        self,
        context: ExecutionContext,
        resource: PolicyResource,
        action: str,
        decision: PolicyDecision,
    ) -> None:
        """Write no resource content, prompts, claims, or credentials."""
        async with self._sessions() as session, session.begin():
            session.add(self._row(context, resource, action, decision))

    async def record_many(
        self,
        context: ExecutionContext,
        records: Sequence[tuple[PolicyResource, PolicyAction, PolicyDecision]],
    ) -> None:
        """Write one bounded policy audit batch in one transaction."""
        if not records:
            return
        async with self._sessions() as session, session.begin():
            session.add_all(
                self._row(context, resource, action.value, decision)
                for resource, action, decision in records
            )

    @staticmethod
    def _row(
        context: ExecutionContext,
        resource: PolicyResource,
        action: str,
        decision: PolicyDecision,
    ) -> PolicyDecisionAuditRow:
        obligations = [
            {"kind": item.kind.value, "value": item.value} for item in decision.obligations
        ]
        return PolicyDecisionAuditRow(
            organization_id=context.organization_id,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            resource_type=resource.resource_type,
            resource_id_hash=hashlib.sha256(resource.resource_id.encode()).hexdigest(),
            action=action,
            allowed=decision.allowed,
            reason_code=decision.reason_code,
            policy_version=decision.policy_version,
            matched_rule_ids_json=json.dumps(decision.matched_rule_ids),
            obligations_json=json.dumps(obligations, separators=(",", ":")),
        )


class BoundedDecisionCache:
    """Process-local TTL cache used only for safe allow decisions."""

    def __init__(self, ttl_seconds: float = 15, maximum_entries: int = 10_000) -> None:
        """Configure strict TTL and size bounds."""
        self._ttl, self._maximum_entries = ttl_seconds, maximum_entries
        self._values: dict[str, tuple[float, PolicyDecision]] = {}

    async def get(self, key: str) -> PolicyDecision | None:
        """Return a non-expired allow decision."""
        item = self._values.get(key)
        if item is None:
            return None
        expires_at, decision = item
        if expires_at <= time.monotonic():
            self._values.pop(key, None)
            return None
        return decision

    async def put(self, key: str, decision: PolicyDecision) -> None:
        """Bound memory and refuse to cache denies."""
        if not decision.allowed:
            return
        if len(self._values) >= self._maximum_entries:
            self._values.pop(next(iter(self._values)))
        self._values[key] = (time.monotonic() + self._ttl, decision)
