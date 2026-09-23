"""Tenant-scoped operational integration models."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class IntegrationProvider(StrEnum):
    """Providers supported by the SaaS connection manager."""

    JIRA = "jira"
    SLACK = "slack"


class ConnectionStatus(StrEnum):
    """Lifecycle state visible without exposing credentials."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ConnectionScope(StrEnum):
    """Whether a connection is shared by a tenant or owned by one actor."""

    ORGANIZATION = "organization"
    PERSONAL = "personal"


class GrantSubjectType(StrEnum):
    """Organization subjects that may receive MCP capabilities."""

    ORGANIZATION = "organization"
    DEPARTMENT = "department"
    TEAM = "team"
    PROJECT = "project"
    AGENT = "agent"
    USER = "user"


class ToolPermission(StrEnum):
    """Increasing integration capability levels."""

    READ = "read"
    DRAFT = "draft"
    EXECUTE = "execute"
    ADMINISTER = "administer"


@dataclass(frozen=True, slots=True)
class IntegrationConnection:
    """Public, secret-free view of one tenant connection."""

    id: UUID
    provider: IntegrationProvider
    name: str
    endpoint_url: str
    scope: ConnectionScope
    status: ConnectionStatus
    organization_id: str
    owner_actor_id: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ResolvedConnection:
    """Infrastructure-only active connection including encrypted authorization."""

    connection: IntegrationConnection
    encrypted_authorization: str


@dataclass(frozen=True, slots=True)
class OAuthStart:
    """Browser redirect produced for a protected OAuth authorization flow."""

    authorization_url: str


@dataclass(frozen=True, slots=True)
class ConnectionToolGrant:
    """One explicit subject/tool permission without credentials."""

    id: UUID
    connection_id: UUID
    organization_id: str
    subject_type: GrantSubjectType
    subject_id: str
    tool_name: str
    permission: ToolPermission
    created_by: str
    created_at: datetime
