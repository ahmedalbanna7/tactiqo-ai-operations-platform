"""SQLAlchemy job ledger with deduplication, fairness, and expiring leases."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tactiqo.jobs.application.policy import require_transition
from tactiqo.jobs.domain.models import (
    Job,
    JobCheckpoint,
    JobKind,
    JobLease,
    JobProgress,
    JobRisk,
    JobStatus,
)
from tactiqo.jobs.infrastructure.tables import (
    JobAttemptRow,
    JobCheckpointRow,
    JobEventRow,
    JobLeaseRow,
    JobRow,
)
from tactiqo.shared.domain.execution import ExecutionContext
from tactiqo.shared.infrastructure.database import session_scope


class ConcurrentJobUpdateError(RuntimeError):
    """Optimistic version changed before the requested update committed."""


class SqlAlchemyJobRepository:
    """PostgreSQL source of truth for background operations."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Configure the repository with a bounded session factory."""
        self._sessions = sessions

    async def create(  # noqa: PLR0913
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
        """Deduplicate executable steps inside a tenant boundary."""
        row = JobRow(
            organization_id=context.organization_id,
            actor_id=context.actor_id,
            run_id=run_id,
            plan_id=plan_id,
            step_id=step_id,
            kind=kind.value,
            risk=risk.value,
            status=JobStatus.QUEUED.value,
            priority=max(0, min(priority, 100)),
            idempotency_key=idempotency_key,
            input_reference=input_reference,
            policy_version=context.policy_version,
            maximum_attempts=maximum_attempts,
        )
        try:
            async with session_scope(self._sessions) as session:
                session.add(row)
                await session.flush()
                await self._event(session, row.id, "job.created", {"kind": kind.value})
                await session.refresh(row)
            return self._job(row), True
        except IntegrityError:
            statement = select(JobRow).where(
                JobRow.organization_id == context.organization_id,
                JobRow.idempotency_key == idempotency_key,
            )
            async with self._sessions() as session:
                existing = await session.scalar(statement)
            if existing is None:
                raise
            return self._job(existing), False

    async def get(self, job_id: UUID, context: ExecutionContext) -> Job | None:
        """Return a job only in its originating actor and tenant scope."""
        statement = select(JobRow).where(
            JobRow.id == job_id,
            JobRow.organization_id == context.organization_id,
            JobRow.actor_id == context.actor_id,
        )
        async with self._sessions() as session:
            row = await session.scalar(statement)
        return self._job(row) if row else None

    async def list(self, context: ExecutionContext, limit: int = 100) -> list[Job]:
        """List only jobs owned by the current actor in the current tenant."""
        statement = (
            select(JobRow)
            .where(
                JobRow.organization_id == context.organization_id,
                JobRow.actor_id == context.actor_id,
            )
            .order_by(JobRow.created_at.desc())
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
        return [self._job(row) for row in rows]

    async def request_cancel(self, job_id: UUID, context: ExecutionContext) -> Job | None:
        """Persist cooperative cancellation without crossing owner scope."""
        async with session_scope(self._sessions) as session:
            row = await session.scalar(
                select(JobRow)
                .where(
                    JobRow.id == job_id,
                    JobRow.organization_id == context.organization_id,
                    JobRow.actor_id == context.actor_id,
                )
                .with_for_update()
            )
            if row is None:
                return None
            if not JobStatus(row.status).terminal:
                row.cancel_requested = True
                if JobStatus(row.status) in {
                    JobStatus.QUEUED,
                    JobStatus.RETRY_SCHEDULED,
                    JobStatus.WAITING_APPROVAL,
                }:
                    require_transition(JobStatus(row.status), JobStatus.CANCELLED)
                    row.status = JobStatus.CANCELLED.value
                    row.progress_stage = "cancelled"
                row.version += 1
                row.updated_at = datetime.now(UTC)
                await self._event(session, row.id, "job.cancel_requested", {})
            await session.flush()
            await session.refresh(row)
        return self._job(row)

    async def acquire(
        self, kind: JobKind, worker_id: str, lease_for: timedelta
    ) -> tuple[Job, JobLease] | None:
        """Lease oldest tenant jobs fairly, then honor priority within that order."""
        now = datetime.now(UTC)
        async with session_scope(self._sessions) as session:
            row = await session.scalar(
                select(JobRow)
                .outerjoin(JobLeaseRow, JobLeaseRow.job_id == JobRow.id)
                .where(
                    JobRow.kind == kind.value,
                    JobRow.status.in_((JobStatus.QUEUED.value, JobStatus.RETRY_SCHEDULED.value)),
                    JobRow.available_at <= now,
                    JobRow.cancel_requested.is_(False),
                    JobLeaseRow.job_id.is_(None),
                )
                .order_by(JobRow.created_at.asc(), JobRow.priority.desc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return None
            require_transition(JobStatus(row.status), JobStatus.RUNNING)
            row.status = JobStatus.RUNNING.value
            row.progress_stage = "leased"
            row.version += 1
            row.updated_at = now
            token = uuid4()
            lease_row = JobLeaseRow(
                job_id=row.id,
                worker_id=worker_id,
                token=token,
                acquired_at=now,
                heartbeat_at=now,
                expires_at=now + lease_for,
            )
            session.add(lease_row)
            attempt_number = (
                int(
                    await session.scalar(
                        select(func.count())
                        .select_from(JobAttemptRow)
                        .where(JobAttemptRow.job_id == row.id)
                    )
                    or 0
                )
                + 1
            )
            session.add(JobAttemptRow(job_id=row.id, number=attempt_number, worker_id=worker_id))
            await self._event(session, row.id, "job.leased", {"attempt": attempt_number})
            await session.flush()
            await session.refresh(row)
            await session.refresh(lease_row)
        return self._job(row), self._lease(lease_row)

    async def heartbeat(self, lease: JobLease, extend_by: timedelta) -> JobLease | None:
        """Extend a live lease only when its unguessable token matches."""
        now = datetime.now(UTC)
        async with session_scope(self._sessions) as session:
            row = await session.scalar(
                select(JobLeaseRow)
                .where(JobLeaseRow.job_id == lease.job_id, JobLeaseRow.token == lease.token)
                .with_for_update()
            )
            if row is None or row.expires_at <= now:
                return None
            row.heartbeat_at = now
            row.expires_at = now + extend_by
            await session.flush()
            await session.refresh(row)
        return self._lease(row)

    async def get_internal(self, job_id: UUID) -> Job | None:
        """Read within the trusted worker process; never expose this through HTTP."""
        async with self._sessions() as session:
            row = await session.get(JobRow, job_id)
        return self._job(row) if row else None

    async def latest_checkpoint(self, job_id: UUID) -> JobCheckpoint | None:
        """Return the newest resumable reference without loading referenced content."""
        statement = (
            select(JobCheckpointRow)
            .where(JobCheckpointRow.job_id == job_id)
            .order_by(JobCheckpointRow.sequence.desc())
            .limit(1)
        )
        async with self._sessions() as session:
            row = await session.scalar(statement)
        if row is None:
            return None
        return JobCheckpoint(
            row.id,
            row.job_id,
            row.attempt_id,
            row.sequence,
            row.stage,
            row.state_reference,
            row.created_at,
        )

    async def attempt_count(self, job_id: UUID) -> int:
        """Count attempts for bounded retry decisions."""
        async with self._sessions() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(JobAttemptRow)
                .where(JobAttemptRow.job_id == job_id)
            )
        return int(count or 0)

    async def update_progress(
        self, lease: JobLease, *, stage: str, completed_units: int, total_units: int | None
    ) -> Job:
        """Update progress only while the supplied lease is current and alive."""
        now = datetime.now(UTC)
        async with session_scope(self._sessions) as session:
            lease_row = await session.scalar(
                select(JobLeaseRow)
                .where(
                    JobLeaseRow.job_id == lease.job_id,
                    JobLeaseRow.token == lease.token,
                    JobLeaseRow.expires_at > now,
                )
                .with_for_update()
            )
            if lease_row is None:
                raise ConcurrentJobUpdateError
            row = await session.get(JobRow, lease.job_id)
            if row is None or JobStatus(row.status) is not JobStatus.RUNNING:
                raise ConcurrentJobUpdateError
            row.progress_stage = stage[:96]
            row.completed_units = max(0, completed_units)
            row.total_units = max(0, total_units) if total_units is not None else None
            row.version += 1
            row.updated_at = now
            await session.flush()
            await session.refresh(row)
        return self._job(row)

    async def save_checkpoint(
        self, lease: JobLease, *, stage: str, state_reference: str
    ) -> JobCheckpoint:
        """Append a checkpoint tied to the current attempt and active lease."""
        async with session_scope(self._sessions) as session:
            active = await session.scalar(
                select(JobLeaseRow).where(
                    JobLeaseRow.job_id == lease.job_id, JobLeaseRow.token == lease.token
                )
            )
            attempt = await session.scalar(
                select(JobAttemptRow)
                .where(JobAttemptRow.job_id == lease.job_id, JobAttemptRow.finished_at.is_(None))
                .order_by(JobAttemptRow.number.desc())
                .limit(1)
            )
            if active is None or attempt is None:
                raise ConcurrentJobUpdateError
            sequence = (
                int(
                    await session.scalar(
                        select(func.coalesce(func.max(JobCheckpointRow.sequence), 0)).where(
                            JobCheckpointRow.job_id == lease.job_id
                        )
                    )
                    or 0
                )
                + 1
            )
            row = JobCheckpointRow(
                job_id=lease.job_id,
                attempt_id=attempt.id,
                sequence=sequence,
                stage=stage[:96],
                state_reference=state_reference[:512],
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
        return JobCheckpoint(
            row.id,
            row.job_id,
            row.attempt_id,
            row.sequence,
            row.stage,
            row.state_reference,
            row.created_at,
        )

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
        """Atomically close an attempt and remove exclusive ownership."""
        now = datetime.now(UTC)
        async with session_scope(self._sessions) as session:
            lease_row = await session.scalar(
                select(JobLeaseRow)
                .where(JobLeaseRow.job_id == lease.job_id, JobLeaseRow.token == lease.token)
                .with_for_update()
            )
            row = await session.get(JobRow, lease.job_id, with_for_update=True)
            if lease_row is None or row is None:
                raise ConcurrentJobUpdateError
            require_transition(JobStatus(row.status), target)
            attempt = await session.scalar(
                select(JobAttemptRow)
                .where(JobAttemptRow.job_id == row.id, JobAttemptRow.finished_at.is_(None))
                .order_by(JobAttemptRow.number.desc())
                .limit(1)
            )
            if attempt:
                attempt.finished_at = now
                attempt.outcome = outcome[:32]
                attempt.failure_code = failure_code[:96] if failure_code else None
            row.status = target.value
            row.progress_stage = stage[:96]
            row.output_reference = output_reference[:512] if output_reference else None
            row.available_at = now + retry_after if retry_after else now
            row.version += 1
            row.updated_at = now
            await session.delete(lease_row)
            await self._event(
                session,
                row.id,
                "job.attempt_finished",
                {
                    "status": target.value,
                    "failure_code": failure_code or "",
                },
            )
            await session.flush()
            await session.refresh(row)
        return self._job(row)

    async def recover_expired(self) -> int:
        """Recover jobs whose workers disappeared, bounded by maximum attempts."""
        now = datetime.now(UTC)
        recovered = 0
        async with session_scope(self._sessions) as session:
            leases = (
                await session.scalars(
                    select(JobLeaseRow)
                    .where(JobLeaseRow.expires_at <= now)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for lease in leases:
                row = await session.get(JobRow, lease.job_id, with_for_update=True)
                if row is None or JobStatus(row.status) is not JobStatus.RUNNING:
                    await session.delete(lease)
                    continue
                attempts = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(JobAttemptRow)
                        .where(JobAttemptRow.job_id == row.id)
                    )
                    or 0
                )
                row.status = (
                    JobStatus.DEAD_LETTER if attempts >= row.maximum_attempts else JobStatus.QUEUED
                ).value
                row.progress_stage = "lease_expired"
                row.version += 1
                row.updated_at = now
                await session.delete(lease)
                await self._event(session, row.id, "job.lease_expired", {"attempts": attempts})
                recovered += 1
        return recovered

    async def retry(self, job_id: UUID, context: ExecutionContext) -> Job | None:
        """Explicit retry in exact tenant and actor scope."""
        async with session_scope(self._sessions) as session:
            row = await session.scalar(
                select(JobRow)
                .where(
                    JobRow.id == job_id,
                    JobRow.organization_id == context.organization_id,
                    JobRow.actor_id == context.actor_id,
                )
                .with_for_update()
            )
            if row is None:
                return None
            require_transition(JobStatus(row.status), JobStatus.QUEUED)
            row.status = JobStatus.QUEUED.value
            row.cancel_requested = False
            row.progress_stage = "manually_retried"
            row.available_at = datetime.now(UTC)
            row.version += 1
            await self._event(session, row.id, "job.manually_retried", {})
            await session.flush()
            await session.refresh(row)
        return self._job(row)

    async def status_counts(self, context: ExecutionContext) -> dict[str, int]:
        """Aggregate only jobs visible to the current actor."""
        statement = (
            select(JobRow.status, func.count())
            .where(
                JobRow.organization_id == context.organization_id,
                JobRow.actor_id == context.actor_id,
            )
            .group_by(JobRow.status)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return {str(status): int(count) for status, count in rows}

    async def transition(
        self,
        job_id: UUID,
        expected_version: int,
        target: JobStatus,
        *,
        stage: str,
    ) -> Job:
        """Apply a validated state transition with optimistic concurrency."""
        async with session_scope(self._sessions) as session:
            current = await session.get(JobRow, job_id)
            if current is None:
                message = "job_not_found"
                raise LookupError(message)
            require_transition(JobStatus(current.status), target)
            now = datetime.now(UTC)
            result = await session.execute(
                update(JobRow)
                .where(JobRow.id == job_id, JobRow.version == expected_version)
                .values(
                    status=target.value,
                    progress_stage=stage,
                    version=expected_version + 1,
                    updated_at=now,
                )
                .returning(JobRow.id)
            )
            if result.scalar_one_or_none() is None:
                raise ConcurrentJobUpdateError
            await self._event(session, job_id, "job.transition", {"status": target.value})
            row = await session.get(JobRow, job_id)
            if row is None:
                message = "job_not_found"
                raise LookupError(message)
        return self._job(row)

    @staticmethod
    async def _event(
        session: AsyncSession, job_id: UUID, event_type: str, payload: dict[str, object]
    ) -> None:
        sequence = (
            int(
                await session.scalar(
                    select(func.coalesce(func.max(JobEventRow.sequence), 0)).where(
                        JobEventRow.job_id == job_id
                    )
                )
                or 0
            )
            + 1
        )
        import json  # noqa: PLC0415 - keep serialization at persistence boundary

        session.add(
            JobEventRow(
                job_id=job_id,
                sequence=sequence,
                event_type=event_type,
                payload_json=json.dumps(payload, separators=(",", ":")),
            )
        )

    @staticmethod
    def _job(row: JobRow) -> Job:
        return Job(
            id=row.id,
            organization_id=row.organization_id,
            actor_id=row.actor_id,
            run_id=row.run_id,
            plan_id=row.plan_id,
            step_id=row.step_id,
            kind=JobKind(row.kind),
            risk=JobRisk(row.risk),
            status=JobStatus(row.status),
            priority=row.priority,
            idempotency_key=row.idempotency_key,
            input_reference=row.input_reference,
            output_reference=row.output_reference,
            policy_version=row.policy_version,
            cancel_requested=row.cancel_requested,
            version=row.version,
            progress=JobProgress(
                row.progress_stage, row.completed_units, row.total_units, row.updated_at
            ),
            maximum_attempts=row.maximum_attempts,
            available_at=row.available_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _lease(row: JobLeaseRow) -> JobLease:
        return JobLease(
            row.job_id,
            row.worker_id,
            row.token,
            row.acquired_at,
            row.heartbeat_at,
            row.expires_at,
        )
