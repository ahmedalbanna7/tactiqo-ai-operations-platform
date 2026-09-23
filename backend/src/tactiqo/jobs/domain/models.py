"""Provider-neutral F5 job, attempt, lease, progress, and artifact models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class JobKind(StrEnum):
    """Queue families isolated by workload and operational risk."""

    DOCUMENT_OCR = "document_ocr"
    MEDIA = "media"
    REPORT_BI = "report_bi"
    INTEGRATION_AUTOMATION = "integration_automation"
    RISK_REVIEW = "risk_review"


class JobRisk(StrEnum):
    """Operational queue risk used for policy and capacity partitioning."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class JobStatus(StrEnum):
    """Deterministic durable job lifecycle."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    RETRY_SCHEDULED = "retry_scheduled"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"

    @property
    def terminal(self) -> bool:
        """Return whether no further automatic work is permitted."""
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED, self.DEAD_LETTER}


@dataclass(frozen=True, slots=True)
class JobProgress:
    """Measurable progress without sensitive output in messages."""

    stage: str
    completed_units: int
    total_units: int | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Job:
    """Tenant-owned durable unit created from one authorized plan step."""

    id: UUID
    organization_id: str
    actor_id: str
    run_id: UUID
    plan_id: UUID
    step_id: str
    kind: JobKind
    risk: JobRisk
    status: JobStatus
    priority: int
    idempotency_key: str
    input_reference: str
    output_reference: str | None
    policy_version: str
    cancel_requested: bool
    version: int
    progress: JobProgress
    maximum_attempts: int
    available_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class JobLease:
    """Time-bounded exclusive ownership of a runnable job."""

    job_id: UUID
    worker_id: str
    token: UUID
    acquired_at: datetime
    heartbeat_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class JobAttempt:
    """One bounded execution attempt with sanitized failure evidence."""

    id: UUID
    job_id: UUID
    number: int
    worker_id: str
    started_at: datetime
    finished_at: datetime | None
    outcome: str | None
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class JobCheckpoint:
    """Opaque resumable state reference for crash recovery."""

    id: UUID
    job_id: UUID
    attempt_id: UUID
    sequence: int
    stage: str
    state_reference: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class JobArtifact:
    """Output lineage linked to its job and attempt."""

    id: UUID
    job_id: UUID
    attempt_id: UUID
    artifact_type: str
    storage_reference: str
    checksum_sha256: str
    classification: str
    created_at: datetime
    expires_at: datetime | None
    metadata: dict[str, str] = field(default_factory=dict)
