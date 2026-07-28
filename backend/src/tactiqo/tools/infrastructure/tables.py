"""SQLAlchemy approval and tool-audit mappings."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tactiqo.chat.infrastructure.tables import utc_now
from tactiqo.shared.infrastructure.database import Base


class ApprovalRequestRow(Base):
    """Persistence model for human tool approvals."""

    __tablename__ = "approval_requests"
    __table_args__ = (UniqueConstraint("run_id", "tool_call_id", name="uq_approval_run_tool_call"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        index=True,
    )
    tool_call_id: Mapped[str] = mapped_column(String(128))
    tool_name: Mapped[str] = mapped_column(String(128))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), index=True)
    actor_id: Mapped[str] = mapped_column(String(128))
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolAuditRow(Base):
    """Append-only audit record for attempted and completed tool actions."""

    __tablename__ = "tool_audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        index=True,
    )
    tool_call_id: Mapped[str] = mapped_column(String(128))
    tool_name: Mapped[str] = mapped_column(String(128))
    phase: Mapped[str] = mapped_column(String(32))
    safe_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(String(128))
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    correlation_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
