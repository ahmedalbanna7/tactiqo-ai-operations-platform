"""SQLAlchemy mapping for tenant-owned integration connections."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tactiqo.chat.infrastructure.tables import utc_now
from tactiqo.shared.infrastructure.database import Base


class IntegrationConnectionRow(Base):
    """Encrypted provider connection scoped to one organization and optional actor."""

    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_integration_connection_org_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(120))
    endpoint_url: Mapped[str] = mapped_column(String(512))
    scope: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), index=True)
    encrypted_authorization: Mapped[str] = mapped_column(String(8192))
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    owner_actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class ConnectionToolGrantRow(Base):
    """Explicit tool capability assigned to one organization subject."""

    __tablename__ = "connection_tool_grants"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "subject_type",
            "subject_id",
            "tool_name",
            name="uq_connection_subject_tool_grant",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    subject_type: Mapped[str] = mapped_column(String(24), index=True)
    subject_id: Mapped[str] = mapped_column(String(128), index=True)
    tool_name: Mapped[str] = mapped_column(String(160))
    permission: Mapped[str] = mapped_column(String(24))
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
