"""Tenant-safe SQLAlchemy mappings for identity and organization hierarchy."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from tactiqo.chat.infrastructure.tables import utc_now
from tactiqo.shared.infrastructure.database import Base


class UserRow(Base):
    """Immutable external subject mapped to an internal identifier."""

    __tablename__ = "identity_users"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_identity_provider_subject"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OrganizationRow(Base):
    """Immutable SaaS tenant boundary."""

    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), index=True, default="active")
    plan: Mapped[str] = mapped_column(String(48), default="free")
    locale: Mapped[str] = mapped_column(String(16), default="ar-EG")
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Cairo")
    data_region: Mapped[str] = mapped_column(String(48), default="global")
    policy_version: Mapped[str] = mapped_column(String(64), default="1")
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OrganizationMemberRow(Base):
    """Dated membership inside exactly one organization."""

    __tablename__ = "organization_members"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(24), index=True)
    classification_clearance: Mapped[str] = mapped_column(String(64), default="internal")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSessionRow(Base):
    """Opaque revocable browser session; only a token hash is stored."""

    __tablename__ = "auth_sessions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    provider_token_id_hash: Mapped[str] = mapped_column(String(64), unique=True)
    assurance: Mapped[str] = mapped_column(String(24))
    user_agent_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthAuditRow(Base):
    """Secret-free authentication security event."""

    __tablename__ = "auth_audit_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("identity_users.id"), nullable=True)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("auth_sessions.id"), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(128), index=True)
    safe_detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InvitationRow(Base):
    """Hashed, expiring organization invitation."""

    __tablename__ = "organization_invitations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    department_id: Mapped[UUID] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(24), index=True, default="pending")
    invited_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RoleDefinitionRow(Base):
    """Stable role definition separate from assignment."""

    __tablename__ = "role_definitions"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    privileged: Mapped[bool] = mapped_column(Boolean, default=False)


class RoleAssignmentRow(Base):
    """Dated and revocable tenant-scoped role assignment."""

    __tablename__ = "role_assignments"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"), index=True
    )
    role_code: Mapped[str] = mapped_column(ForeignKey("role_definitions.code"))
    scope_type: Mapped[str] = mapped_column(String(24), default="organization")
    scope_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[UUID | None] = mapped_column(ForeignKey("identity_users.id"), nullable=True)


class DepartmentRow(Base):
    """Organization department and its accountable manager."""

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_department_org_code"),
        UniqueConstraint("organization_id", "id", name="uq_department_org_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    manager_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("identity_users.id"), nullable=True
    )
    classification_ceiling: Mapped[str] = mapped_column(String(64), default="internal")
    status: Mapped[str] = mapped_column(String(24), default="active")


class DepartmentMemberRow(Base):
    """Employee membership required for active operational access."""

    __tablename__ = "department_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "department_id"],
            ["departments.organization_id", "departments.id"],
            ondelete="CASCADE",
        ),
    )
    organization_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    department_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"), primary_key=True
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeamRow(Base):
    """Optional team bounded by one department."""

    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_team_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "department_id"],
            ["departments.organization_id", "departments.id"],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    department_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String(160))
    manager_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("identity_users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="active")


class TeamMemberRow(Base):
    """Team membership that remains bounded by department membership."""

    __tablename__ = "team_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["teams.organization_id", "teams.id"],
            ondelete="CASCADE",
        ),
    )
    organization_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"), primary_key=True
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectRow(Base):
    """Project/domain owned by one department without expanding its scope."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_project_org_code"),
        UniqueConstraint("organization_id", "id", name="uq_project_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "department_id"],
            ["departments.organization_id", "departments.id"],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    department_id: Mapped[UUID]
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    manager_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("identity_users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="active")


class ProjectMemberRow(Base):
    """Matrix project membership with no implicit department membership."""

    __tablename__ = "project_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    organization_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"), primary_key=True
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantLifecycleRequestRow(Base):
    """Durable approval request for owner transfer/export/deletion."""

    __tablename__ = "tenant_lifecycle_requests"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), index=True, default="pending")
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("identity_users.id"), nullable=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index(
    "ix_role_assignment_effective",
    RoleAssignmentRow.organization_id,
    RoleAssignmentRow.user_id,
    RoleAssignmentRow.revoked_at,
)
