"""Vendor-neutral RBAC, ABAC, and ReBAC policy vocabulary."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class PolicyAction(StrEnum):
    """Stable platform actions compiled independently."""

    VISIBLE = "visible"
    USE = "use"
    READ = "read"
    DRAFT = "draft"
    EXECUTE = "execute"
    PUBLISH = "publish"
    ADMINISTER = "administer"
    APPROVE = "approve"
    EXPORT = "export"


class PolicyEffect(StrEnum):
    """A rule either allows or explicitly denies."""

    ALLOW = "allow"
    DENY = "deny"


class PolicyObligationType(StrEnum):
    """Enforcement work required after an allow decision."""

    APPROVAL = "approval"
    REDACTION = "redaction"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    STEP_UP = "step_up"


@dataclass(frozen=True, slots=True)
class PolicyObligation:
    """Sanitized obligation and non-secret configuration."""

    kind: PolicyObligationType
    value: str


@dataclass(frozen=True, slots=True)
class PolicyResource:
    """Resource attributes supplied by a trusted server adapter."""

    resource_type: str
    resource_id: str
    organization_id: str
    classification: str = "internal"
    owner_actor_id: str | None = None
    department_id: str | None = None
    team_id: str | None = None
    project_id: str | None = None
    geography: str = "global"


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """One versioned rule combining role, attributes, and relationships."""

    rule_id: str
    policy_version: str
    effect: PolicyEffect
    actions: frozenset[PolicyAction]
    resource_types: frozenset[str]
    resource_ids: frozenset[str] = field(default_factory=frozenset)
    role_codes: frozenset[str] = field(default_factory=frozenset)
    actor_ids: frozenset[str] = field(default_factory=frozenset)
    department_ids: frozenset[str] = field(default_factory=frozenset)
    team_ids: frozenset[str] = field(default_factory=frozenset)
    project_ids: frozenset[str] = field(default_factory=frozenset)
    subject_department_ids: frozenset[str] = field(default_factory=frozenset)
    subject_team_ids: frozenset[str] = field(default_factory=frozenset)
    subject_project_ids: frozenset[str] = field(default_factory=frozenset)
    geography: frozenset[str] = field(default_factory=frozenset)
    classification_ceiling: str = "restricted"
    owner_only: bool = False
    utc_hour_start: int | None = None
    utc_hour_end: int | None = None
    obligations: tuple[PolicyObligation, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Explainable decision safe for enforcement and audit."""

    allowed: bool
    reason_code: str
    policy_version: str
    matched_rule_ids: tuple[str, ...] = field(default_factory=tuple)
    obligations: tuple[PolicyObligation, ...] = field(default_factory=tuple)
    decided_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EffectiveToolGrantSummary:
    """Secret-free integration capability visible to one resolved subject."""

    provider: str
    connection_name: str
    tool_name: str
    permission: str


@dataclass(frozen=True, slots=True)
class OrganizationUnitScope:
    """Tenant-validated unit relationships needed for non-persistent preview only."""

    kind: str
    unit_id: str
    department_id: str | None
    descendant_team_ids: tuple[str, ...] = ()
    descendant_project_ids: tuple[str, ...] = ()
