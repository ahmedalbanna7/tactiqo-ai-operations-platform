"""Deterministic deny-by-default RBAC + ABAC + ReBAC compiler."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime

from tactiqo.authorization.application.ports import (
    DecisionAuditPort,
    DecisionCachePort,
    PolicyRepository,
)
from tactiqo.authorization.domain.models import (
    PolicyAction,
    PolicyDecision,
    PolicyEffect,
    PolicyResource,
    PolicyRule,
)
from tactiqo.shared.domain.execution import ExecutionContext

CLASSIFICATION_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}


class PolicyCompiler:
    """Compile current subject, attributes, and relationships into one decision."""

    def __init__(
        self,
        repository: PolicyRepository,
        audit: DecisionAuditPort,
        cache: DecisionCachePort,
    ) -> None:
        """Configure authoritative rules, sanitized audit, and safe cache."""
        self._repository = repository
        self._audit = audit
        self._cache = cache

    async def decide(
        self,
        context: ExecutionContext,
        resource: PolicyResource,
        action: PolicyAction,
        now: datetime | None = None,
    ) -> PolicyDecision:
        """Apply explicit-deny precedence and otherwise require a matching allow."""
        if resource.organization_id != context.organization_id:
            return await self._record(
                context,
                resource,
                action,
                PolicyDecision(
                    allowed=False,
                    reason_code="scope_mismatch",
                    policy_version=context.policy_version,
                ),
            )
        key = self._cache_key(context, resource, action)
        timestamp = now or datetime.now(UTC)
        rules = await self._repository.list_rules(context.organization_id, context.policy_version)
        has_time_condition = any(
            rule.utc_hour_start is not None or rule.utc_hour_end is not None for rule in rules
        )
        if not has_time_condition:
            cached = await self._cache.get(key)
            if cached is not None:
                return cached
        matches = [
            rule for rule in rules if self._matches(rule, context, resource, action, timestamp)
        ]
        denies = sorted(rule.rule_id for rule in matches if rule.effect is PolicyEffect.DENY)
        if denies:
            decision = PolicyDecision(
                allowed=False,
                reason_code="explicit_deny",
                policy_version=context.policy_version,
                matched_rule_ids=tuple(denies),
                decided_at=timestamp,
            )
        else:
            allows = sorted(
                (rule for rule in matches if rule.effect is PolicyEffect.ALLOW),
                key=lambda rule: rule.rule_id,
            )
            if not allows:
                decision = PolicyDecision(
                    allowed=False,
                    reason_code="default_deny",
                    policy_version=context.policy_version,
                    decided_at=timestamp,
                )
            else:
                obligations = tuple(
                    dict.fromkeys(obligation for rule in allows for obligation in rule.obligations)
                )
                decision = PolicyDecision(
                    allowed=True,
                    reason_code="allowed",
                    policy_version=context.policy_version,
                    matched_rule_ids=tuple(rule.rule_id for rule in allows),
                    obligations=obligations,
                    decided_at=timestamp,
                )
                if not has_time_condition:
                    await self._cache.put(key, decision)
        return await self._record(context, resource, action, decision)

    async def decide_many(
        self,
        context: ExecutionContext,
        requests: Sequence[tuple[PolicyResource, PolicyAction]],
    ) -> list[PolicyDecision]:
        """Evaluate a batch with one rule read and a batched audit write when supported."""
        if not requests:
            return []
        timestamp = datetime.now(UTC)
        rules = await self._repository.list_rules(context.organization_id, context.policy_version)
        has_time_condition = any(
            rule.utc_hour_start is not None or rule.utc_hour_end is not None for rule in rules
        )
        results: list[PolicyDecision] = []
        audit_records: list[tuple[PolicyResource, PolicyAction, PolicyDecision]] = []
        for resource, action in requests:
            if resource.organization_id != context.organization_id:
                decision = PolicyDecision(
                    allowed=False,
                    reason_code="scope_mismatch",
                    policy_version=context.policy_version,
                    decided_at=timestamp,
                )
                results.append(decision)
                audit_records.append((resource, action, decision))
                continue
            key = self._cache_key(context, resource, action)
            cached = await self._cache.get(key) if not has_time_condition else None
            if cached is not None:
                results.append(cached)
                continue
            matches = [
                rule
                for rule in rules
                if self._matches(rule, context, resource, action, timestamp)
            ]
            denies = sorted(rule.rule_id for rule in matches if rule.effect is PolicyEffect.DENY)
            if denies:
                decision = PolicyDecision(
                    allowed=False,
                    reason_code="explicit_deny",
                    policy_version=context.policy_version,
                    matched_rule_ids=tuple(denies),
                    decided_at=timestamp,
                )
            else:
                allows = sorted(
                    (rule for rule in matches if rule.effect is PolicyEffect.ALLOW),
                    key=lambda rule: rule.rule_id,
                )
                if not allows:
                    decision = PolicyDecision(
                        allowed=False,
                        reason_code="default_deny",
                        policy_version=context.policy_version,
                        decided_at=timestamp,
                    )
                else:
                    obligations = tuple(
                        dict.fromkeys(
                            obligation for rule in allows for obligation in rule.obligations
                        )
                    )
                    decision = PolicyDecision(
                        allowed=True,
                        reason_code="allowed",
                        policy_version=context.policy_version,
                        matched_rule_ids=tuple(rule.rule_id for rule in allows),
                        obligations=obligations,
                        decided_at=timestamp,
                    )
                    if not has_time_condition:
                        await self._cache.put(key, decision)
            results.append(decision)
            audit_records.append((resource, action, decision))
        record_many = getattr(self._audit, "record_many", None)
        if callable(record_many):
            await record_many(context, audit_records)
        else:
            for resource, action, decision in audit_records:
                await self._audit.record(context, resource, action.value, decision)
        return results

    async def _record(
        self,
        context: ExecutionContext,
        resource: PolicyResource,
        action: PolicyAction,
        decision: PolicyDecision,
    ) -> PolicyDecision:
        await self._audit.record(context, resource, action.value, decision)
        return decision

    @staticmethod
    def _matches(  # noqa: C901, PLR0911, PLR0912 - explicit fail-closed matrix
        rule: PolicyRule,
        context: ExecutionContext,
        resource: PolicyResource,
        action: PolicyAction,
        now: datetime,
    ) -> bool:
        if rule.policy_version != context.policy_version:
            return False
        if action not in rule.actions or resource.resource_type not in rule.resource_types:
            return False
        if rule.resource_ids and resource.resource_id not in rule.resource_ids:
            return False
        if rule.role_codes and not rule.role_codes.intersection(context.role_codes):
            return False
        if rule.actor_ids and context.actor_id not in rule.actor_ids:
            return False
        if rule.department_ids and (
            resource.department_id not in rule.department_ids
            or resource.department_id not in context.department_ids
        ):
            return False
        if rule.team_ids and (
            resource.team_id not in rule.team_ids or resource.team_id not in context.team_ids
        ):
            return False
        if rule.project_ids and (
            resource.project_id not in rule.project_ids
            or resource.project_id not in context.project_ids
        ):
            return False
        if rule.subject_department_ids and not rule.subject_department_ids.intersection(
            context.department_ids
        ):
            return False
        if rule.subject_team_ids and not rule.subject_team_ids.intersection(context.team_ids):
            return False
        if rule.subject_project_ids and not rule.subject_project_ids.intersection(
            context.project_ids
        ):
            return False
        if rule.geography and resource.geography not in rule.geography:
            return False
        if rule.owner_only and resource.owner_actor_id != context.actor_id:
            return False
        resource_rank = CLASSIFICATION_RANK.get(resource.classification)
        ceiling_rank = CLASSIFICATION_RANK.get(rule.classification_ceiling)
        clearance_rank = CLASSIFICATION_RANK.get(context.classification_clearance)
        if resource_rank is None or ceiling_rank is None or clearance_rank is None:
            return False
        if resource_rank > min(ceiling_rank, clearance_rank):
            return False
        return not (
            rule.utc_hour_start is not None
            and rule.utc_hour_end is not None
            and not rule.utc_hour_start <= now.hour < rule.utc_hour_end
        )

    @staticmethod
    def _cache_key(
        context: ExecutionContext,
        resource: PolicyResource,
        action: PolicyAction,
    ) -> str:
        values = {
            "actor": context.actor_id,
            "organization": context.organization_id,
            "policy_version": context.policy_version,
            "roles": sorted(context.role_codes),
            "departments": sorted(context.department_ids),
            "teams": sorted(context.team_ids),
            "projects": sorted(context.project_ids),
            "clearance": context.classification_clearance,
            "assurance": context.session_assurance,
            "resource": asdict(resource),
            "action": action.value,
        }
        body = json.dumps(values, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()
