"""PostgreSQL mappings for versioned policies and sanitized decisions."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from tactiqo.chat.infrastructure.tables import utc_now
from tactiqo.shared.infrastructure.database import Base


class PolicyRuleRow(Base):
    """One tenant-owned versioned RBAC/ABAC/ReBAC rule."""

    __tablename__ = "authorization_policy_rules"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    policy_version: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(160))
    effect: Mapped[str] = mapped_column(String(16))
    actions_json: Mapped[str] = mapped_column(Text)
    resource_types_json: Mapped[str] = mapped_column(Text)
    resource_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    role_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    actor_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    department_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    team_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    project_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    geography_json: Mapped[str] = mapped_column(Text, default="[]")
    classification_ceiling: Mapped[str] = mapped_column(String(32), default="restricted")
    owner_only: Mapped[bool] = mapped_column(Boolean, default=False)
    utc_hour_start: Mapped[int | None] = mapped_column(nullable=True)
    utc_hour_end: Mapped[int | None] = mapped_column(nullable=True)
    obligations_json: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PolicyDecisionAuditRow(Base):
    """Sanitized policy decision explanation without protected content."""

    __tablename__ = "authorization_decision_audit"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str] = mapped_column(String(128), index=True)
    correlation_id: Mapped[str] = mapped_column(String(128), index=True)
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id_hash: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    allowed: Mapped[bool] = mapped_column(Boolean)
    reason_code: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(64))
    matched_rule_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    obligations_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


Index(
    "ix_policy_rules_effective",
    PolicyRuleRow.organization_id,
    PolicyRuleRow.policy_version,
    PolicyRuleRow.active,
)
