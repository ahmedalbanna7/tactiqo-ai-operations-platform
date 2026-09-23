"""Provider-neutral identity and organization domain values."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class SessionAssurance(StrEnum):
    """Authentication assurance available to authorization policy."""

    STANDARD = "standard"
    MFA = "mfa"
    STEP_UP = "step_up"


class MembershipStatus(StrEnum):
    """Organization membership lifecycle."""

    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class OrganizationRole(StrEnum):
    """Stable built-in role codes; assignments remain separate records."""

    OWNER = "owner"
    ORGANIZATION_ADMIN = "organization_admin"
    INTEGRATION_MANAGER = "integration_manager"
    DEPARTMENT_MANAGER = "department_manager"
    TEAM_MANAGER = "team_manager"
    PROJECT_MANAGER = "project_manager"
    EMPLOYEE = "employee"
    AUDITOR_RISK_REVIEWER = "auditor_risk_reviewer"


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Verified external subject mapped to an immutable internal user."""

    user_id: UUID
    provider: str
    subject: str
    session_id: UUID
    assurance: SessionAssurance
    authenticated_at: datetime


@dataclass(frozen=True, slots=True)
class EffectiveMembership:
    """Server-derived organization hierarchy visible to one principal."""

    organization_id: str
    policy_version: str
    data_region: str
    classification_clearance: str
    role_codes: tuple[str, ...] = field(default_factory=tuple)
    department_ids: tuple[str, ...] = field(default_factory=tuple)
    team_ids: tuple[str, ...] = field(default_factory=tuple)
    project_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class VerifiedIdentityToken:
    """Minimum claims accepted from an OIDC ID token."""

    issuer: str
    subject: str
    audience: str
    nonce: str
    token_id: str
    expires_at: datetime
    authenticated_at: datetime
    assurance: SessionAssurance
