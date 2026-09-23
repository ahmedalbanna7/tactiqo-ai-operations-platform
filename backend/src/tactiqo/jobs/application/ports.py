"""Durable job persistence and queue contracts."""

from datetime import timedelta
from typing import Protocol
from uuid import UUID

from tactiqo.jobs.domain.models import Job, JobCheckpoint, JobKind, JobLease, JobRisk, JobStatus
from tactiqo.shared.domain.execution import ExecutionContext


class JobRepository(Protocol):
    """Persist job truth with tenant scope and optimistic concurrency."""

    async def create(  # noqa: PLR0913 - explicit immutable job command fields
        self,
        *,
        run_id: UUID,
        plan_id: UUID,
        step_id: str,
        kind: JobKind,
        risk: JobRisk,
        idempotency_key: str,
        input_reference: str,
        context: ExecutionContext,
        priority: int = 50,
        maximum_attempts: int = 3,
    ) -> tuple[Job, bool]:
        """Create once per tenant/idempotency key and report whether inserted."""

    async def get(self, job_id: UUID, context: ExecutionContext) -> Job | None:
        """Return a job only to its originating actor and tenant."""

    async def list(self, context: ExecutionContext, limit: int = 100) -> list[Job]:
        """List visible jobs newest first."""

    async def request_cancel(self, job_id: UUID, context: ExecutionContext) -> Job | None:
        """Persist cooperative cancellation in exact owner scope."""

    async def acquire(
        self, kind: JobKind, worker_id: str, lease_for: timedelta
    ) -> tuple[Job, JobLease] | None:
        """Lease one fair runnable job with skip-locked semantics."""

    async def heartbeat(self, lease: JobLease, extend_by: timedelta) -> JobLease | None:
        """Extend only the matching active lease token."""

    async def get_internal(self, job_id: UUID) -> Job | None:
        """Return a job to the trusted worker boundary only."""

    async def latest_checkpoint(self, job_id: UUID) -> JobCheckpoint | None:
        """Return the latest opaque resume reference for a worker."""

    async def attempt_count(self, job_id: UUID) -> int:
        """Return the number of started attempts."""

    async def update_progress(
        self, lease: JobLease, *, stage: str, completed_units: int, total_units: int | None
    ) -> Job:
        """Persist measurable progress only for the active lease."""

    async def save_checkpoint(
        self, lease: JobLease, *, stage: str, state_reference: str
    ) -> JobCheckpoint:
        """Persist an opaque resumable reference for the current attempt."""

    async def finish_attempt(  # noqa: PLR0913 - explicit atomic completion fields
        self,
        lease: JobLease,
        target: JobStatus,
        *,
        stage: str,
        outcome: str,
        failure_code: str | None = None,
        output_reference: str | None = None,
        retry_after: timedelta | None = None,
    ) -> Job:
        """Close the active attempt and release its lease atomically."""

    async def recover_expired(self) -> int:
        """Return abandoned running work to retry or dead-letter state."""

    async def retry(self, job_id: UUID, context: ExecutionContext) -> Job | None:
        """Explicitly requeue an actor-owned failed or dead-letter job."""

    async def status_counts(self, context: ExecutionContext) -> dict[str, int]:
        """Return tenant-and-actor scoped lifecycle counts."""

    async def transition(
        self,
        job_id: UUID,
        expected_version: int,
        target: JobStatus,
        *,
        stage: str,
    ) -> Job:
        """Apply a validated optimistic state transition."""


class JobPublisher(Protocol):
    """Publish reference-only work notifications."""

    async def publish(self, job: Job, work_envelope: str) -> None:
        """Publish job identifiers and signed authority, never raw input."""
