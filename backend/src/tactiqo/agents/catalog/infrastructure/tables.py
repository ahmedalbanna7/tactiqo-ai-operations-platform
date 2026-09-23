"""PostgreSQL mappings for versioned agents and tenant assignments."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from tactiqo.chat.infrastructure.tables import utc_now
from tactiqo.shared.infrastructure.database import Base


class AgentDefinitionRow(Base):
    """Global stable identity and category for one agent."""

    __tablename__ = "agent_definitions"
    code: Mapped[str] = mapped_column(String(96), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), index=True)


class AgentVersionRow(Base):
    """Immutable agent prompt/config/capability contract."""

    __tablename__ = "agent_versions"
    agent_code: Mapped[str] = mapped_column(
        ForeignKey("agent_definitions.code", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt_template: Mapped[str] = mapped_column(Text)
    configuration_json: Mapped[str] = mapped_column(Text, default="{}")
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    input_schema_json: Mapped[str] = mapped_column(Text, default="{}")
    output_schema_json: Mapped[str] = mapped_column(Text, default="{}")
    risk: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OrganizationAgentRow(Base):
    """Installed version lifecycle inside exactly one tenant."""

    __tablename__ = "organization_agents"
    __table_args__ = (UniqueConstraint("organization_id", "agent_code", name="uq_org_agent"),)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    agent_code: Mapped[str] = mapped_column(ForeignKey("agent_definitions.code"), primary_key=True)
    version: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    installed_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AgentAssignmentRow(Base):
    """Agent relation to organization, role, department, team, project, or user."""

    __tablename__ = "agent_assignments"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_code: Mapped[str] = mapped_column(String(96))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(128))
    classification_ceiling: Mapped[str] = mapped_column(String(32), default="internal")
    data_domains_json: Mapped[str] = mapped_column(Text, default="[]")
    quota_json: Mapped[str] = mapped_column(Text, default="{}")
    budget_json: Mapped[str] = mapped_column(Text, default="{}")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    assigned_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_agent_assignment_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "agent_code"],
            ["organization_agents.organization_id", "organization_agents.agent_code"],
            ondelete="CASCADE",
        ),
    )


class AgentActionGrantRow(Base):
    """Separate action grant or explicit deny for one assignment."""

    __tablename__ = "agent_action_grants"
    organization_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    assignment_id: Mapped[UUID] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(32), primary_key=True)
    effect: Mapped[str] = mapped_column(String(16), default="allow")
    obligations_json: Mapped[str] = mapped_column(Text, default="[]")
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assignment_id"],
            ["agent_assignments.organization_id", "agent_assignments.id"],
            ondelete="CASCADE",
        ),
    )


class AgentAttachmentRow(Base):
    """Allowed data domain, MCP connection, or individual tool attachment."""

    __tablename__ = "agent_assignment_attachments"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(String(128))
    assignment_id: Mapped[UUID] = mapped_column()
    attachment_type: Mapped[str] = mapped_column(String(32))
    reference_id: Mapped[str] = mapped_column(String(160))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "assignment_id"],
            ["agent_assignments.organization_id", "agent_assignments.id"],
            ondelete="CASCADE",
        ),
    )


class AgentApprovalChainRow(Base):
    """Approval chain selected by agent, action, risk, and target system."""

    __tablename__ = "agent_approval_chains"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    agent_code: Mapped[str] = mapped_column(ForeignKey("agent_definitions.code"))
    action: Mapped[str] = mapped_column(String(32))
    risk: Mapped[str] = mapped_column(String(24))
    target_system: Mapped[str] = mapped_column(String(96), default="*")
    chain_json: Mapped[str] = mapped_column(Text)
