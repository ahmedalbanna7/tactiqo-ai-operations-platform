"""PostgreSQL truth tables for AI provider profiles and accounting."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from tactiqo.shared.infrastructure.database import Base


class AIProviderProfileRow(Base):
    """One tenant-owned versioned capability profile."""

    __tablename__ = "ai_provider_profiles"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(96))
    kind: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(256))
    endpoint: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(24))
    version: Mapped[int] = mapped_column(Integer, default=1)
    secret_reference: Mapped[str | None] = mapped_column(String(256))
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=90)
    maximum_retries: Mapped[int] = mapped_column(Integer, default=1)
    maximum_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    daily_unit_limit: Mapped[int] = mapped_column(BigInteger, default=100_000)
    classifications_json: Mapped[str] = mapped_column(Text, default="[]")
    capabilities_json: Mapped[str] = mapped_column(Text, default='["general"]')
    routing_priority: Mapped[int] = mapped_column(Integer, default=100)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("organization_id", "name"),)


class AIProviderUsageRow(Base):
    """Sanitized per-call accounting without content or credentials."""

    __tablename__ = "ai_provider_usage"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    profile_name: Mapped[str] = mapped_column(String(96))
    latency_ms: Mapped[int] = mapped_column(Integer)
    units: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(96))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AIProviderCredentialRow(Base):
    """Encrypted local-development credential addressed by an opaque reference."""

    __tablename__ = "ai_provider_credentials"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    reference: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(64))
    encrypted_secret: Mapped[str] = mapped_column(Text)
    last_four: Mapped[str] = mapped_column(String(4))
    created_by: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
