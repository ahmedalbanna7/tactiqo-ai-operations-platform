"""PostgreSQL mappings for the durable F5 job ledger."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tactiqo.chat.infrastructure.tables import utc_now
from tactiqo.shared.infrastructure.database import Base


class JobRow(Base):
    """Durable tenant-owned background job with optimistic versioning."""

    __tablename__ = "background_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_job_org_idempotency"),
        Index("ix_job_runnable", "status", "available_at", "priority"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[str] = mapped_column(String(128), index=True)
    actor_id: Mapped[str] = mapped_column(String(128), index=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    plan_id: Mapped[UUID] = mapped_column(index=True)
    step_id: Mapped[str] = mapped_column(String(96))
    kind: Mapped[str] = mapped_column(String(48), index=True)
    risk: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    input_reference: Mapped[str] = mapped_column(String(512))
    output_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(64))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    progress_stage: Mapped[str] = mapped_column(String(96), default="queued")
    completed_units: Mapped[int] = mapped_column(Integer, default=0)
    total_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class JobLeaseRow(Base):
    """Exclusive expiring worker ownership."""

    __tablename__ = "background_job_leases"
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("background_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    worker_id: Mapped[str] = mapped_column(String(128), index=True)
    token: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class JobAttemptRow(Base):
    """Sanitized history of bounded job attempts."""

    __tablename__ = "background_job_attempts"
    __table_args__ = (UniqueConstraint("job_id", "number", name="uq_job_attempt_number"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("background_jobs.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(96), nullable=True)


class JobCheckpointRow(Base):
    """Ordered resumable state references."""

    __tablename__ = "background_job_checkpoints"
    __table_args__ = (UniqueConstraint("job_id", "sequence", name="uq_job_checkpoint_sequence"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("background_jobs.id", ondelete="CASCADE"), index=True
    )
    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("background_job_attempts.id", ondelete="CASCADE")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(96))
    state_reference: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class JobArtifactRow(Base):
    """MinIO-backed artifact lineage and retention metadata."""

    __tablename__ = "background_job_artifacts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("background_jobs.id", ondelete="CASCADE"), index=True
    )
    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("background_job_attempts.id", ondelete="CASCADE")
    )
    artifact_type: Mapped[str] = mapped_column(String(64))
    storage_reference: Mapped[str] = mapped_column(String(512))
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    classification: Mapped[str] = mapped_column(String(32))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobEventRow(Base):
    """Content-free append-only operations audit."""

    __tablename__ = "background_job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence", name="uq_job_event_sequence"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("background_jobs.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
